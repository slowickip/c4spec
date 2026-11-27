import assert from 'node:assert/strict';
import { test } from 'node:test';
import { compareModels, selectProject } from '../dist/model.js';

const endpoint = { source: 'app', target: 'db' };
const read = { ...endpoint, title: 'Reads' };
const write = { ...endpoint, title: 'Writes' };

function model(relations = {}, views = {}) {
  return { projectId: 'project', elements: {}, relations, views };
}

test('computed delta preserves parallel edge counts and reports safe one-to-one edits', () => {
  const parallel = compareModels(model({ a: read, b: read, c: write }), model({ x: read, y: write }));
  assert.deepEqual(parallel.relationships.removed, [{ relationship: read, count: 1 }]);
  assert.deepEqual(parallel.relationships.modified, []);
  const change = compareModels(model({ a: read }), model({ z: { ...read, technology: 'SQL' } }));
  assert.deepEqual(change.relationships.modified[0].fieldChanges.technology, {
    beforePresent: false, afterPresent: true, before: null, after: 'SQL',
  });
});

test('computed views ignore generated IDs and layout, while keeping the order of dynamic steps', () => {
  function graph(first, second, prefix, reverse) {
    const readEdge = prefix + 'READ';
    const writeEdge = prefix + 'WRITE';
    const flow = reverse ? [writeEdge, readEdge] : [readEdge, writeEdge];
    return model({ [first]: read, [second]: write }, {
      interactions: {
        id: 'interactions',
        _type: 'dynamic',
        nodes: [{ id: 'app', x: first.length }, { id: 'db' }],
        edges: [
          { id: readEdge, ...endpoint, relations: [first] },
          { id: writeEdge, ...endpoint, relations: [second] },
        ],
        flow: [{ _type: 'parallel', flow }],
      },
    });
  }
  const initial = graph('x', 'y', 'A', false);
  assert.equal(compareModels(initial, graph('otherA', 'otherB', 'B', false)).changed, false);
  assert.deepEqual(compareModels(initial, graph('otherA', 'otherB', 'B', true)).views.modified, ['interactions']);
});

test('project selection deduplicates equivalent exports and requires a choice for distinct projects', () => {
  const first = model();
  const second = { ...first, projectId: 'another' };
  assert.deepEqual(selectProject([first, first]), first);
  assert.throws(() => selectProject([first, second]), /Multiple LikeC4 projects/);
  assert.deepEqual(selectProject([first, second], 'another'), second);
});
