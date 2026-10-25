'use strict';
/*
 * Run an instrumented JavaScript snippet and print a JSON execution trace.
 *
 * Invoked by tracing/js_tracer.py as `node runtime.js`, with a JSON request on
 * stdin: {"original", "instrumented", "sites", "max_steps"}. The instrumented
 * code calls back into the probe object `__T` (passed in as a parameter):
 *
 *   __T.s(site, getter)    before a statement / loop iteration  -> "line" step
 *   __T.c(site, getter)    at function entry, returns a frame   -> "call" step
 *   __T.r(site, value)     wraps a returned value               -> "return" step
 *   __T.l(frame)           in the function's finally            -> implicit return + pop
 *
 * `getter(k)` reads the k-th name of the site's scope through a closure placed
 * at the probe point, so it sees exactly the bindings visible there; reading a
 * let/const still in its temporal dead zone throws and the name is skipped.
 *
 * Only Node builtins are used. Output format: see tracing/__init__.py.
 */

const fs = require('fs');
const vm = require('vm');
const util = require('util');
const { createRequire } = require('module');

const MAX_ITEMS = 64;
const MAX_DEPTH = 12;
const ASYNC_GRACE_MS = 1000;

// Builtins captured before user code runs, so a snippet that overrides
// prototypes cannot break (or re-enter) the encoder.
const getProto = Object.getPrototypeOf;
const ownKeys = Object.keys;
const getOwnDesc = Object.getOwnPropertyDescriptor;
const isArray = Array.isArray;
const isView = ArrayBuffer.isView;
const mapEntries = Map.prototype.entries;
const setValues = Set.prototype.values;
const isProxy = util.types.isProxy;
const isMap = util.types.isMap;
const isSet = util.types.isSet;
const isDate = util.types.isDate;
const isRegExp = util.types.isRegExp;
const formatWithOptions = util.formatWithOptions;
const ObjectProto = Object.prototype;
const realStdoutWrite = process.stdout.write.bind(process.stdout);

const LIMIT = Symbol('step limit');

const request = JSON.parse(fs.readFileSync(0, 'utf8'));
const sites = request.sites;
const maxSteps = request.max_steps | 0 || 1500;

const steps = [];
const result = { language: 'javascript', steps, error: null, truncated: false };
const ids = new Map(); // object -> stable heap id for the whole run
let nextId = 1;
let captured = '';
let printed = 0;
let busy = false; // inside the tracer itself: ignore probes (getters, inspect hooks)
const moduleFrame = { func: '<module>', getter: null, names: [], lastLine: -1, lastSite: -1, returned: false };
const frames = [moduleFrame];

// ---------------------------------------------------------------- encoding

function heapId(obj) {
  let id = ids.get(obj);
  if (id === undefined) {
    id = String(nextId++);
    ids.set(obj, id);
  }
  return id;
}

function dictKey(key) {
  // Plain objects coerce every key to a string; give canonical numeric keys
  // back their number so graph[1] and a neighbor 1 are the same node.
  if (typeof key === 'string' && key !== '' && String(Number(key)) === key) return Number(key);
  return key;
}

function className(obj) {
  try {
    const proto = getProto(obj);
    if (!proto) return 'Object';
    const desc = getOwnDesc(proto, 'constructor');
    const ctor = desc && desc.value;
    return (typeof ctor === 'function' && ctor.name) || 'Object';
  } catch (_) {
    return 'Object';
  }
}

function dataFields(obj) {
  const fields = [];
  for (const key of ownKeys(obj)) {
    const desc = getOwnDesc(obj, key);
    if (desc && 'value' in desc) fields.push([key, desc.value]);
    if (fields.length >= MAX_ITEMS) break;
  }
  return fields;
}

class Encoder {
  constructor() {
    this.heap = {};
  }

  encode(value, depth = 0) {
    switch (typeof value) {
      case 'undefined':
        return null;
      case 'boolean':
      case 'string':
        return value;
      case 'number':
        if (Number.isNaN(value)) return 'NaN';
        if (value === Infinity) return '∞';
        if (value === -Infinity) return '-∞';
        return value === 0 ? 0 : value; // -0 -> 0
      case 'bigint': {
        const n = Number(value);
        return Number.isSafeInteger(n) ? n : String(value);
      }
      case 'symbol':
        return value.toString();
      case 'function':
        return `ƒ ${value.name || 'anonymous'}`;
      default:
        break;
    }
    if (value === null) return null;
    if (depth > MAX_DEPTH) return '…';

    const ref = heapId(value);
    if (ref in this.heap) return { ref };
    this.heap[ref] = {}; // reserve first so cycles terminate
    let obj;
    try {
      obj = this.describe(value, depth + 1);
    } catch (_) {
      obj = { kind: 'object', class: 'Object', fields: {} };
    }
    this.heap[ref] = obj;
    return { ref };
  }

  describe(value, depth) {
    if (isProxy(value)) return { kind: 'object', class: 'Proxy', fields: {} };
    if (isArray(value) || (isView(value) && !(value instanceof DataView))) {
      const n = Math.min(value.length, MAX_ITEMS);
      const items = [];
      for (let i = 0; i < n; i++) items.push(this.encode(value[i], depth));
      return { kind: 'list', items };
    }
    if (isMap(value)) {
      const entries = [];
      for (const [k, v] of mapEntries.call(value)) {
        if (entries.length >= MAX_ITEMS) break;
        entries.push([this.encode(k, depth), this.encode(v, depth)]);
      }
      return { kind: 'dict', entries };
    }
    if (isSet(value)) {
      // Insertion order is meaningful in JS (unlike Python sets), keep it.
      const items = [];
      for (const v of setValues.call(value)) {
        if (items.length >= MAX_ITEMS) break;
        items.push(this.encode(v, depth));
      }
      return { kind: 'set', items };
    }
    const proto = getProto(value);
    if (proto === ObjectProto || proto === null) {
      // Object literals are the JS map: {1: [2, 3]}, {")": "("}.
      const entries = dataFields(value).map(([k, v]) => [dictKey(k), this.encode(v, depth)]);
      return { kind: 'dict', entries };
    }
    if (isDate(value) || isRegExp(value)) {
      return { kind: 'object', class: className(value), fields: { value: String(value) } };
    }
    const fields = {};
    for (const [k, v] of dataFields(value)) fields[k] = this.encode(v, depth);
    if (value instanceof Error) fields.message = String(value.message);
    return { kind: 'object', class: className(value), fields };
  }
}

// ------------------------------------------------------------------ steps

function frameLocals(frame, encoder) {
  const locals = {};
  if (!frame.getter) return locals;
  const names = frame.names;
  for (let i = 0; i < names.length; i++) {
    let value;
    try {
      value = frame.getter(i);
    } catch (_) {
      continue; // temporal dead zone: declared but not yet initialized
    }
    if (value === undefined || typeof value === 'function') continue;
    if (names[i] === 'this' && (value === null || value === globalThis)) continue;
    locals[names[i]] = encoder.encode(value);
  }
  return locals;
}

function record(event, line, returnValue) {
  if (steps.length >= maxSteps) {
    result.truncated = true;
    throw LIMIT;
  }
  busy = true;
  try {
    const encoder = new Encoder();
    const stack = frames.map((f) => ({ func: f.func, locals: frameLocals(f, encoder) }));
    const step = {
      line,
      event,
      func: stack[stack.length - 1].func,
      stack,
      heap: encoder.heap,
    };
    if (event === 'return') step.return_value = encoder.encode(returnValue);
    if (captured.length > printed) {
      step.stdout = captured.slice(printed);
      printed = captured.length;
    }
    steps.push(step);
  } finally {
    busy = false;
  }
}

const probes = {
  s(id, getter) {
    if (busy) return;
    if (result.truncated) throw LIMIT;
    const site = sites[id];
    const frame = frames[frames.length - 1];
    frame.getter = getter;
    frame.names = site.names;
    frame.line = site.line;
    if (site.quiet) {
      // Loop header whose body shares its line: on a new iteration let the
      // body's probe record (the header runs after `i++`, values look off).
      if (id < frame.lastSite) frame.lastLine = -1;
      frame.lastSite = id;
      return;
    }
    // Like Python's line events: one step per line, plus one each time
    // control jumps back (loop iterations), not one per statement.
    const sameLine = site.line === frame.lastLine && id > frame.lastSite;
    frame.lastLine = site.line;
    frame.lastSite = id;
    if (!sameLine) record('line', site.line);
  },

  c(id, getter) {
    const site = sites[id];
    const frame = { func: site.func, getter, names: site.names, line: site.line, lastLine: -1, lastSite: -1, returned: false };
    if (busy) {
      frame.skip = true;
      return frame;
    }
    if (result.truncated) throw LIMIT;
    frames.push(frame);
    record('call', site.line);
    return frame;
  },

  r(id, value) {
    if (busy) return value;
    const frame = frames[frames.length - 1];
    if (frame === moduleFrame) return value;
    frame.returned = true;
    record('return', sites[id].line, value);
    return value;
  },

  l(frame) {
    if (frame.skip) return;
    const index = frames.lastIndexOf(frame);
    if (index < 0) return;
    if (!frame.returned && !result.truncated && !busy) {
      // Fell off the end (or an exception is propagating): Python reports a
      // return of None here; never throw from a finally block.
      if (steps.length >= maxSteps) result.truncated = true;
      else record('return', frame.line, undefined);
    }
    frames.length = index;
  },
};

// ----------------------------------------------------------------- output

function capture(...args) {
  const wasBusy = busy;
  busy = true;
  try {
    captured += formatWithOptions({ colors: false }, ...args) + '\n';
  } finally {
    busy = wasBusy;
  }
}

console.log = capture;
console.info = capture;
console.debug = capture;
console.dir = (value) => capture(value);
console.table = capture;
console.error = () => {};
console.warn = () => {};
console.trace = () => {};
process.stdout.write = (chunk) => {
  captured += String(chunk);
  return true;
};

function errorMessage(err) {
  if (err instanceof Error) return `${err.name}: ${err.message}`;
  try {
    return `Uncaught ${util.inspect(err)}`;
  } catch (_) {
    return 'Uncaught exception';
  }
}

function syntaxError(err) {
  const match = /^[^\n]*:(\d+)\n/.exec(String(err && err.stack));
  const where = match ? ` (line ${match[1]})` : '';
  return `SyntaxError: ${err.message}${where}`;
}

let finished = false;
function finish() {
  if (finished) return;
  finished = true;
  result.stdout = captured.slice(-4000);
  let text;
  try {
    text = JSON.stringify(result);
  } catch (err) {
    text = JSON.stringify({ language: 'javascript', steps: [], error: `Tracer failed: ${err.message}`, truncated: false });
  }
  realStdoutWrite(text, () => process.exit(0));
}

function onAsyncError(err) {
  if (err !== LIMIT && !result.error) result.error = errorMessage(err);
  finish();
}

// -------------------------------------------------------------------- run

const PARAMS = ['require', 'module', 'exports'];
const filename = 'snippet.js';

function main() {
  try {
    vm.compileFunction(request.original, PARAMS, { filename });
  } catch (err) {
    result.error = syntaxError(err);
    return finish();
  }

  let program;
  try {
    program = vm.compileFunction(request.instrumented, ['__T', ...PARAMS], { filename });
  } catch (err) {
    result.error = `Tracer could not instrument this code: ${err.message}`;
    return finish();
  }

  process.on('uncaughtException', onAsyncError);
  process.on('unhandledRejection', onAsyncError);

  const mod = { exports: {} };
  try {
    program.call(mod.exports, probes, createRequire(__filename), mod, mod.exports);
  } catch (err) {
    if (err !== LIMIT) result.error = errorMessage(err);
  }
  if (result.error || result.truncated) return finish();

  // Let promise chains and timers the snippet started run to completion,
  // but never wait on a timer that keeps the process alive forever.
  process.on('beforeExit', finish);
  setTimeout(finish, ASYNC_GRACE_MS).unref();
}

main();
