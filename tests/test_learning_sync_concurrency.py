"""Run against an isolated PostgreSQL test database after p0_learning_sync.sql.

PGHOST=/tmp PGPORT=55438 PGUSER=postgres python3 tests/test_learning_sync_concurrency.py
Optional --fixture PATH benchmarks a locally saved master snapshot, without printing it.
Fixture rows are removed; this script never modifies existing learner rows.
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import shutil
import subprocess
import time
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--psql', default=shutil.which('psql') or '/opt/homebrew/opt/postgresql@17/bin/psql')
parser.add_argument('--fixture')
options = parser.parse_args()
args = [options.psql, '-h', os.environ.get('PGHOST', '/tmp'), '-p', os.environ.get('PGPORT', '55438'),
        '-U', os.environ.get('PGUSER', 'postgres'), '-d', os.environ.get('PGDATABASE', 'postgres'),
        '-v', 'ON_ERROR_STOP=1', '-At']


def sql(statement):
    result = subprocess.run(args, input=statement, text=True, capture_output=True)
    if result.returncode:
        # PostgreSQL can include the private fixture payload in its error context.
        raise RuntimeError('PostgreSQL test failed: ' + result.stderr.splitlines()[0])
    return result.stdout


def quote(value):
    return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"


def run_fixture(master, benchmark=False):
    uid = str(uuid.uuid4())
    pid = 'reader_' + uid
    profile = next(iter(master['appState']['users'].values()))
    profile['id'] = pid
    master['appState']['users'] = {pid: profile}
    master['appState']['currentUserId'] = pid
    word_id = str(profile['words'][0]['id'])
    previous_count = profile['words'][0].get('correctCount', 0)
    previous_events = len(profile.get('studyEvents', []))
    created = False

    def sync(payload, hold_lock=False):
        lock_delay = 'select pg_sleep(0.2);' if hold_lock else ''
        return sql(f"begin; set local role authenticated; select set_config('request.jwt.claim.sub','{uid}',true); "
                   f"select public.sync_vocab_master_v3({quote(payload)},gen_random_uuid(),null)->>'revision'; "
                   f"{lock_delay} commit;")

    def client(index):
        payload = json.loads(json.dumps(master))
        payload['appState']['users'][pid]['studyEvents'] = [{
            'id': f'{uid}-concurrent-{index}', 'wordId': word_id, 'durableVersion': 3,
            'at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'result': 'correct'}]
        return sync(payload, True)

    try:
        start = time.monotonic()
        sql(f"begin; insert into auth.users(id,email) values('{uid}','{uid}@example.invalid'); "
            f"insert into public.reader_sync_state(user_id,vocab_master_progress) values('{uid}',{quote(master)}); commit;")
        created = True
        if benchmark:
            print(f'Fixture seed: {time.monotonic() - start:.3f}s')
            start = time.monotonic()
            sync(master)
            print(f'Fixture unchanged sync: {time.monotonic() - start:.3f}s')
        start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(client, range(2)))
        actual = sql(f"select (select w->>'correctCount' from jsonb_array_elements(vocab_master_progress#>'{{appState,users,{pid},words}}') w where w->>'id'='{word_id}'), "
                     f"(select count(*) from public.vocab_learning_events where user_id='{uid}') "
                     f"from public.reader_sync_state where user_id='{uid}';").strip()
        expected = f'{previous_count + 2}|{previous_events + 2}'
        assert actual == expected, f'Concurrent counters/journal {actual}, expected {expected}'
        print(f'PASS: two concurrent stale snapshots preserve both answers exactly once ({time.monotonic() - start:.3f}s).')
    finally:
        if created:
            sql(f"begin; delete from public.reader_sync_state where user_id='{uid}'; "
                f"delete from public.vocab_learning_events where user_id='{uid}'; "
                f"delete from public.vocab_snapshot_archive where user_id='{uid}'; "
                f"delete from public.vocab_sync_metadata where user_id='{uid}'; "
                f"delete from auth.users where id='{uid}'; commit;")


run_fixture({'appState': {'users': {'fixture': {
    'words': [{'id': 'w', 'english_word': 'test', 'correctCount': 3, 'incorrectCount': 2, 'consecutiveCorrect': 0}],
    'studyEvents': [{'id': 'baseline', 'wordId': 'w', 'result': 'incorrect',
                     'at': (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)).isoformat()}]
}}}})
if options.fixture:
    with open(options.fixture, encoding='utf-8') as handle:
        fixture = json.load(handle)
    run_fixture(fixture.get('vocab_master_progress', fixture), benchmark=True)
