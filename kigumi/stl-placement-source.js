const fs = require('fs');

/** Apply an already validated edit only while disk and editor still match its source. */
async function applyPlacementEdit(host, edit) {
    const document = await host.getDocumentState(edit.path);
    if (document.isDirty) throw new Error('The source has unsaved edits. Save it and refresh the frame first.');
    if (fs.readFileSync(edit.path, 'utf8') !== edit.expected) {
        throw new Error('The source changed while placing the STL. Refresh the frame first.');
    }
    fs.writeFileSync(edit.path, edit.updated, 'utf8');
}
module.exports = { applyPlacementEdit };
