/**
 * The web version's loading card: in the welcome area until Kigumi is ready (transport.js says when),
 * a log parade, a progress bar through the start-up steps the worker reports, and the
 * steps ticked off. The bar creeps on within a step, so a slow download never looks stuck.
 */
(function () {
    'use strict';

    // The worker's start-up steps (worker/main.js bootPython), and the share of the bar each ends at.
    const STEPS = [
        { label: 'Python', end: 40 },
        { label: 'kumiki’s packages', end: 75 },
        { label: 'kumiki', end: 92 },
        { label: 'Kigumi', end: 99 },
    ];
    const reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let card = null;
    let step = -1;
    let shown = 0;
    let timer = null;

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (text) node.textContent = text;
        return node;
    }

    function build() {
        const welcome = document.getElementById('welcome');
        if (!welcome || card) return;
        card = el('div', 'kw-loading');
        card.id = 'kw-loading';

        const parade = el('div', 'kw-parade');
        parade.setAttribute('aria-hidden', 'true');
        for (const emoji of ['🪵', '🪵', '🪵', '🪵', '🪵', '🪵']) parade.appendChild(el('span', null, emoji));

        const track = el('div', 'kw-load-track');
        track.id = 'kw-load-track';
        track.setAttribute('role', 'progressbar');
        track.setAttribute('aria-label', 'Starting Kigumi');
        track.setAttribute('aria-valuemin', '0');
        track.setAttribute('aria-valuemax', '100');
        const fill = el('div', 'kw-load-fill');
        fill.id = 'kw-load-fill';
        const rider = el('span', 'kw-load-rider', '🦫');
        rider.setAttribute('aria-hidden', 'true');
        fill.appendChild(rider);
        track.appendChild(fill);

        const now = el('p', 'kw-load-step', 'Getting started…');
        now.id = 'kw-load-step';
        now.setAttribute('aria-live', 'polite');
        const detail = el('p', 'kw-load-detail');
        detail.id = 'kw-load-detail';

        const list = el('ol', 'kw-load-steps');
        list.id = 'kw-load-steps';
        for (const { label } of STEPS) list.appendChild(el('li', null, label));

        const note = el('p', 'kw-load-note', 'The first visit downloads Python into your browser, so it takes a minute. Later visits are quicker.');

        card.append(parade, track, now, detail, list, note);
        welcome.insertBefore(card, document.getElementById('welcome-lead'));
        document.body.classList.add('kw-is-loading');
        if (!reducedMotion) timer = setInterval(creep, 250);
        render();
    }

    /** Within a step, move a little toward its end, slower the closer it gets. */
    function creep() {
        if (step < 0) return;
        const end = STEPS[Math.min(step, STEPS.length - 1)].end;
        shown += Math.max(0, end - 1 - shown) * 0.02;
        render();
    }

    function render() {
        if (!card) return;
        const fill = document.getElementById('kw-load-fill');
        fill.style.width = `${shown.toFixed(1)}%`;
        document.getElementById('kw-load-track').setAttribute('aria-valuenow', String(Math.round(shown)));
        [...document.getElementById('kw-load-steps').children].forEach((item, i) => {
            item.className = i < step ? 'is-done' : i === step ? 'is-current' : '';
        });
    }

    /** The worker began start-up step `index` (STEPS), saying `text`; `detail` is a package it loaded. */
    function update(text, index, detail) {
        build();
        if (typeof index === 'number' && index >= 0) {
            if (index !== step) {
                step = index;
                shown = Math.max(shown, index > 0 ? STEPS[index - 1].end : 2);
            }
            // Each package loaded is a step within the step.
            if (detail) shown = Math.min(STEPS[step].end - 1, shown + (STEPS[step].end - shown) * 0.15);
        }
        if (text) document.getElementById('kw-load-step').textContent = text;
        if (detail !== undefined) document.getElementById('kw-load-detail').textContent = detail || '';
        render();
    }

    function done() {
        if (timer) clearInterval(timer);
        timer = null;
        document.body.classList.remove('kw-is-loading');
        if (card) card.remove();
        card = null;
    }

    function fail(message) {
        build();
        if (timer) clearInterval(timer);
        timer = null;
        card.classList.add('is-failed');
        document.getElementById('kw-load-step').textContent = message;
        document.getElementById('kw-load-detail').textContent = 'Reload the page to try again. The Log at the bottom right has the details.';
    }

    window.kigumiLoading = { update, done, fail };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
    else build();
}());
