// Which layout the shell shows: chosen once, when it starts (shell.js).

/** 'phone' on a small touch screen where the host offers it, else 'desktop'; `?layout=` overrides. */
export function chooseLayout({ offered, asked, coarsePointer, shortestSide }) {
    if (asked && offered.includes(asked)) return asked;
    return offered.includes('phone') && coarsePointer && shortestSide <= 600 ? 'phone' : 'desktop';
}
