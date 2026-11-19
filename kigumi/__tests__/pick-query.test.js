// What a click and a hover ask the runner (frame-view-session.js pickQuery). The viewer's request
// went through rebuilt field by field, and four fields were dropped that way, each time leaving
// picks quietly wrong: tolerances, heldGeometry, look and space.
const { pickQuery } = require('../frame-view-session');

const request = {
    type: 'hoverFeatureAtPoint', request: 7,
    memberKey: 'post', point: [0, 0, 1], currentPath: ['body'], ctrlClick: false, candidateIndex: 2,
    tolerances: { face: 0.01 }, ray: { origin: [0, 0, 5], direction: [0, 0, -1] },
    heldGeometry: { kind: 'face' }, heldAt: [1, 0, 0], heldReference: { name: 'top' },
    look: [0, 0, -1], right: [1, 0, 0], up: [0, 1, 0], space: 'sheet', drawnMembers: ['post'],
};

test('every field the viewer sends reaches the runner, a new one too, but not the routing', () => {
    const query = pickQuery({ ...request, somethingNew: 3 });
    const { type: _type, request: _request, ...asked } = request;
    expect(query).toEqual({ ...asked, somethingNew: 3 });
});

test('null stays "choose for me", and zero stays the first feature', () => {
    expect(pickQuery({ ...request, candidateIndex: 0 }).candidateIndex).toBe(0);
    expect(pickQuery({ ...request, candidateIndex: undefined }).candidateIndex).toBeNull();
});

test('a bare request still has a path to start from, and is no ctrl-click', () => {
    expect(pickQuery({ memberKey: 'post', point: [0, 0, 0] })).toEqual({
        memberKey: 'post', point: [0, 0, 0], currentPath: [], ctrlClick: false, candidateIndex: null,
    });
});
