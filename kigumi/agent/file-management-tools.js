const { z } = require('zod');

/** Return the tools that delete and rename files in the open project (write_file makes new ones). */
function createFileManagementTools({ files }) {
    const filePath = z.string().min(1).describe('A path relative to the open project, or an absolute path inside it.');
    const text = (value) => [{ type: 'text', text: value }];
    return [
        {
            name: 'delete_file',
            description: 'Delete one file from the open project. Refuses directories and missing files.',
            shape: { file_path: filePath },
            effect: 'edit',
            run: async ({ file_path: file }) => text(`Deleted ${files.relative(await files.deleteFile(file))}.`),
        },
        {
            name: 'rename_file',
            description: 'Rename or move one file within the open project, making parent folders as needed. Refuses to overwrite the destination.',
            shape: { file_path: filePath, new_path: filePath },
            effect: 'edit',
            run: async ({ file_path: file, new_path: destination }) => text(`Renamed ${file} to ${files.relative(await files.rename(file, destination))}.`),
        },
    ];
}

module.exports = { createFileManagementTools };
