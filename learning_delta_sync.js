/* Incremental wire protocol. The canonical cache is separate from unconfirmed UI state. */
(function (root) {
  'use strict';
  const stable = value => JSON.stringify(value, (_key, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
  const clone = value => JSON.parse(JSON.stringify(value));
  const fault = message => Object.assign(new Error(message), { syncHealthCode: 'receipt_invalid' });
  const profileMeta = user => Object.fromEntries(Object.entries(user || {}).filter(([key]) =>
    !['id', 'words', 'studyEvents', 'rewardLedger', 'ignoredReadingWordIds'].includes(key)));
  const create = () => {
    const accounts = new Map();
    const seed = (accountId, saved) => {
      if (!saved || !saved.epoch || !Number.isInteger(saved.revision) || !saved.master?.appState?.users?.[`reader_${accountId}`]) return false;
      accounts.set(accountId, clone(saved));
      return true;
    };
    const apply = (accountId, response) => {
      const previous = accounts.get(accountId);
      if (!response?.epoch || !Number.isInteger(response.revision) || !Array.isArray(response.words)
          || !Array.isArray(response.events) || !Array.isArray(response.tombstones)
          || !Array.isArray(response.acknowledgedEventIds) || typeof response.full !== 'boolean' || typeof response.hasMore !== 'boolean') throw fault('增量同步回执格式无效');
      if (!response.full && (!previous || previous.epoch !== response.epoch || response.revision < previous.revision)) throw fault('增量同步基线不匹配');
      const id = `reader_${accountId}`;
      const old = response.full ? {} : previous.master.appState.users[id];
      const words = new Map((old.words || []).map(word => [String(word.id), word]));
      const events = new Map((old.studyEvents || []).map(event => [event.id, event]));
      const ignored = new Set(response.full ? response.profile?.ignoredReadingWordIds || [] : old.ignoredReadingWordIds || []);
      for (const word of response.words) {
        if (!word || typeof word.id !== 'string') throw fault('增量词条缺少编号');
        words.set(word.id, word);
      }
      for (const wordId of response.tombstones) { ignored.add(wordId); words.delete(wordId); }
      for (const event of response.events) {
        if (!event?.id || !event.wordId || !['correct', 'incorrect'].includes(event.result)) throw fault('增量答案格式无效');
        const known = events.get(event.id);
        if (known && ['wordId', 'at', 'result'].some(key => known[key] !== event[key])) throw fault('增量答案编号冲突');
        events.set(event.id, event);
      }
      const rewards = { ...(old.rewardLedger || {}), ...(response.profile?.rewardLedger || {}) };
      for (const event of response.events) if (Number.isInteger(event.rewardPoints) && event.rewardPoints > 0 && event.rewardPoints <= 15) rewards[event.id] = event.rewardPoints;
      const user = { ...old, ...response.profile, id, words: [...words.values()],
        studyEvents: [...events.values()].sort((a, b) => a.at.localeCompare(b.at) || a.id.localeCompare(b.id)),
        rewardLedger: rewards, ignoredReadingWordIds: [...ignored] };
      const progress = Object.fromEntries(user.words.filter(word => word.source === 'reading').map(word => [word.english_word.toLowerCase(), {
        correctCount: word.correctCount || 0, incorrectCount: word.incorrectCount || 0,
        consecutiveCorrect: word.consecutiveCorrect || 0, mistakeCleared: Boolean(word.mistakeCleared), flashcardKnown: Boolean(word.flashcardKnown),
        readingIntroducedAt: word.readingIntroducedAt || '', readingNextDueAt: word.readingNextDueAt || '',
        readingMasteredAt: word.readingMasteredAt || '', readingReviewStage: word.readingReviewStage || 0, updatedAt: word.vocabMasterProgressUpdatedAt || ''
      }]));
      const master = { version: 3, words: progress, appState: { version: 1, currentUserId: id, users: { [id]: user }, savedAt: user.updatedAt || '' } };
      const saved = { epoch: response.epoch, revision: response.revision, master };
      accounts.set(accountId, saved);
      return saved;
    };
    const snapshot = accountId => accounts.has(accountId) ? clone(accounts.get(accountId)) : null;
    const read = async ({ accountId, rpc, isCurrentAccount = () => true, onCache = async () => {} }) => {
      while (true) {
        const previous = accounts.get(accountId);
        let reply = await rpc('read_vocab_delta_v4', { p_after_revision: previous?.revision ?? null, p_expected_epoch: previous?.epoch ?? null });
        if (reply.error && ['VMEPOCH', 'VMREVISION'].includes(reply.error.details || reply.error.detail)) {
          reply = await rpc('read_vocab_delta_v4', { p_after_revision: null, p_expected_epoch: null });
        }
        if (reply.error) throw reply.error;
        if (!isCurrentAccount()) return null;
        const response = Array.isArray(reply.data) ? reply.data[0] : reply.data;
        const saved = apply(accountId, response);
        await onCache(snapshot(accountId));
        if (!response.hasMore) return saved;
        if (previous && saved.epoch === previous.epoch && saved.revision <= previous.revision) throw fault('增量分页游标没有前进');
      }
    };
    const changes = (accountId, appState, pending) => {
      const previous = accounts.get(accountId);
      if (!previous) throw fault('增量同步尚未取得基线');
      const id = `reader_${accountId}`;
      const user = appState?.users?.[id];
      if (!user) throw fault('增量同步账号不匹配');
      const canonical = previous.master.appState.users[id];
      const oldWords = new Map(canonical.words.map(word => [word.id, stable(word)]));
      const confirmed = new Map(canonical.studyEvents.map(event => [event.id, event]));
      const events = new Map();
      for (const event of [...(user.studyEvents || []), ...pending]) {
        const old = confirmed.get(event.id);
        if (old) {
          if (['wordId', 'at', 'result'].some(key => old[key] !== event[key])) throw fault('本地答案与云端编号冲突');
        } else events.set(event.id, event);
      }
      for (const event of pending) events.set(event.id, event); // Ambiguous replies still require a fresh journal receipt.
      const alreadyIgnored = new Set(canonical.ignoredReadingWordIds || []);
      const patch = { words: user.words.filter(word => oldWords.get(word.id) !== stable(word)), events: [...events.values()],
        tombstones: (user.ignoredReadingWordIds || []).filter(id => !alreadyIgnored.has(id)) };
      if (stable(profileMeta(user)) !== stable(profileMeta(canonical))) patch.profile = profileMeta(user);
      return patch;
    };
    const batches = patch => {
      const result = [];
      let current = { words: [], events: [], tombstones: [] };
      const bytes = value => new TextEncoder().encode(JSON.stringify(value)).byteLength;
      const push = () => { result.push(current); current = { words: [], events: [], tombstones: [] }; };
      for (const key of ['words', 'events', 'tombstones']) for (const item of patch[key]) {
        const candidate = { ...current, [key]: [...current[key], item] };
        if (current[key].length === 50 || bytes(candidate) > 100 * 1024) push();
        current[key].push(item);
        if (bytes(current) > 100 * 1024) throw new Error('单条学习资料超过增量同步大小限制，本机原件已保留');
      }
      if (patch.profile) {
        if (bytes({ ...current, profile: patch.profile }) > 100 * 1024) push();
        current.profile = patch.profile;
        if (bytes(current) > 100 * 1024) throw new Error('学习设置超过增量同步大小限制，本机原件已保留');
      }
      if (current.words.length || current.events.length || current.tombstones.length || current.profile || !result.length) push();
      return result;
    };
    const sync = async ({ accountId, appState, events = [], rpc, rebase = (_remote, local) => local, isCurrentAccount = () => true, onCache = async () => {} }) => {
      let local = appState;
      if (!accounts.has(accountId)) {
        const fresh = await read({ accountId, rpc, isCurrentAccount, onCache });
        if (!fresh) return null;
        local = rebase(fresh.master.appState, local);
      }
      for (let attempt = 0; attempt < 4; attempt++) {
        const patch = changes(accountId, local, events);
        const acknowledgements = new Set();
        let conflict = false;
        for (const batch of batches(patch)) {
          const base = accounts.get(accountId);
          const reply = await rpc('sync_vocab_delta_v4', { p_changes: batch, p_mutation_id: root.crypto.randomUUID(),
            p_expected_epoch: base.epoch, p_expected_revision: base.revision });
          if (reply.error && ['VMREVISION', 'VMEPOCH'].includes(reply.error.details || reply.error.detail)) {
            const fresh = await read({ accountId, rpc, isCurrentAccount, onCache });
            if (!fresh) return null;
            local = rebase(fresh.master.appState, local);
            conflict = true;
            break;
          }
          if (reply.error) throw reply.error;
          if (!isCurrentAccount()) return null;
          const response = Array.isArray(reply.data) ? reply.data[0] : reply.data;
          if (response?.hasMore) throw fault('写入回执不应包含未读取的分页');
          const saved = apply(accountId, response);
          const returned = new Set(saved.master.appState.users[`reader_${accountId}`].studyEvents.map(event => event.id));
          if (batch.events.some(event => !response.acknowledgedEventIds.includes(event.id) || !returned.has(event.id))) throw fault('云端尚未确认本次增量答案');
          for (const id of response.acknowledgedEventIds) acknowledgements.add(id);
          await onCache(snapshot(accountId));
        }
        if (!conflict) return { ...accounts.get(accountId), acknowledgedEventIds: [...acknowledgements] };
      }
      throw new Error('学习档案正在被其他页面更新，本机记录保留，稍后重试');
    };
    return { seed, snapshot, read, sync, changes };
  };
  root.VocabDeltaSync = { create, stable };
  if (typeof module !== 'undefined') module.exports = root.VocabDeltaSync;
})(typeof globalThis !== 'undefined' ? globalThis : window);
