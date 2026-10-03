import { createMonitorHandler } from './monitor.mjs';

Deno.serve(createMonitorHandler({ env: name => Deno.env.get(name), fetch: globalThis.fetch }));
