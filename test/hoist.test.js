'use strict';
/**
 * 代理核心逻辑的单元测试（零依赖，只用 node:test + node:assert）。
 *
 *   node --test test/
 */
const test = require('node:test');
const assert = require('node:assert');

const { hoistDefs, normalizeResponse } = require('../proxy/coros-mcp-proxy.js');

/** 复刻 COROS 的实际写法：$defs 在子 schema 里，$ref 指文档根。 */
function brokenSchema() {
  return {
    type: 'object',
    properties: {
      course: {
        type: 'object',
        $defs: { Section: { type: 'object', properties: { reps: { type: 'integer' } } } },
        properties: {
          sections: { type: 'array', items: { $ref: '#/$defs/Section' } },
        },
      },
    },
  };
}

test('把嵌套的 $defs 提升到 schema 根', () => {
  const schema = brokenSchema();
  const count = hoistDefs(schema, 'createScheduledWorkout');

  assert.equal(count, 1);
  assert.deepEqual(schema.$defs.Section.properties.reps, { type: 'integer' });
  assert.equal(schema.properties.course.$defs, undefined, '嵌套的 $defs 应被删除');
  assert.equal(
    schema.properties.course.properties.sections.items.$ref,
    '#/$defs/Section',
    '$ref 不该被改写'
  );
});

test('根上已有的 $defs 保持不动', () => {
  const schema = {
    type: 'object',
    $defs: { Keep: { type: 'string' } },
    properties: { x: { $ref: '#/$defs/Keep' } },
  };
  const count = hoistDefs(schema, 'root-only');

  assert.equal(count, 0);
  assert.deepEqual(schema.$defs, { Keep: { type: 'string' } });
});

test('同名但不同结构的 $defs 改名而不是覆盖', () => {
  const schema = {
    type: 'object',
    properties: {
      a: { $defs: { Thing: { type: 'string' } } },
      b: { $defs: { Thing: { type: 'number' } } },
    },
  };
  const count = hoistDefs(schema, 'collision');

  assert.equal(count, 2);
  assert.deepEqual(schema.$defs.Thing, { type: 'string' });
  assert.deepEqual(schema.$defs['Thing$nested'], { type: 'number' });
});

test('同名且结构相同的 $defs 只提升一次', () => {
  const schema = {
    type: 'object',
    properties: {
      a: { $defs: { Same: { type: 'string' } } },
      b: { $defs: { Same: { type: 'string' } } },
    },
  };
  const count = hoistDefs(schema, 'duplicate');

  assert.equal(count, 1);
  assert.deepEqual(Object.keys(schema.$defs), ['Same']);
});

test('没有 $defs 的 schema 一个字节都不改', () => {
  const schema = {
    type: 'object',
    properties: { name: { type: 'string' }, items: { type: 'array', items: { type: 'string' } } },
  };
  const before = JSON.stringify(schema);

  assert.equal(hoistDefs(schema, 'clean'), 0);
  assert.equal(JSON.stringify(schema), before);
});

test('只处理 tools/list 响应，别的消息原样放过', () => {
  const listResponse = {
    jsonrpc: '2.0',
    id: 2,
    result: { tools: [{ name: 'createScheduledWorkout', inputSchema: brokenSchema() }] },
  };
  normalizeResponse(listResponse);
  assert.ok(listResponse.result.tools[0].inputSchema.$defs.Section);

  const callResponse = { jsonrpc: '2.0', id: 3, result: { content: [{ type: 'text', text: 'ok' }] } };
  const before = JSON.stringify(callResponse);
  normalizeResponse(callResponse);
  assert.equal(JSON.stringify(callResponse), before);
});
