// Read-only transport: receiving words never approves or imports them.
(function (root) {
  async function read(rpc, isCurrent = () => true) {
    let after = '';
    const entries = new Map();
    while (isCurrent()) {
      const { data, error } = await rpc('read_reader_vocabulary_for_review_v1', { p_after: after, p_limit: 50 });
      if (!isCurrent()) return null;
      if (error) throw error;
      if (!data || !Array.isArray(data.entries)) throw new Error('阅读生词响应格式错误');
      for (const entry of data.entries) {
        const key = String(entry?.word || '').trim().toLowerCase();
        if (key) entries.set(key, entry);
      }
      if (!data.hasMore) return [...entries.values()];
      if (typeof data.nextAfter !== 'string' || data.nextAfter <= after) throw new Error('阅读生词分页未前进');
      after = data.nextAfter;
    }
    return null;
  }
  root.ReadingInbox = { read };
  if (typeof module !== 'undefined') module.exports = root.ReadingInbox;
})(globalThis);
