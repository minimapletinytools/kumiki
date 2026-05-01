const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

/**
 * Detects if a Python file is a patternbook by checking for:
 * - `patternbook = ...` at module level
 * - `create_*_patternbook(...)` function definition
 * @param {string} fileContent
 * @returns {boolean}
 */
function isPatternbookFile(fileContent) {
    if (/^\s*patternbook\s*=/m.test(fileContent)) return true;
    if (/^\s*def\s+create_\w+_patternbook\s*\(/m.test(fileContent)) return true;
    return false;
}

/**
 * Extracts patternbook name from a file path or content.
 * Returns the filename without extension for now.
 * @param {string} sourceFile
 * @returns {string}
 */
function getPatternbookName(sourceFile) {
    return path.basename(sourceFile, '.py');
}

/**
 * Opens a file in the workspace or shows it as read-only if it's from dependencies.
 * @param {vscode.Uri} fileUri - The file URI to open
 * @param {boolean} readOnly - Whether to open as read-only
 */
async function openFileInEditor(fileUri, readOnly = false) {
    try {
        const doc = await vscode.workspace.openTextDocument(fileUri);
        const editor = await vscode.window.showTextDocument(doc);
        
        if (readOnly) {
            // VS Code doesn't have a direct API to make a document read-only,
            // but we can show a message and disable editing via command
            await vscode.commands.executeCommand('workbench.action.files.setActiveEditorReadonlyInSession');
        }
        
        return editor;
    } catch (error) {
        throw new Error(`Failed to open file: ${error.message}`);
    }
}

/**
 * Copies a file from dependency to workspace patterns folder.
 * @param {string} sourceFile - The source file path
 * @param {string} workspaceRoot - The workspace root directory
 * @param {boolean} isReadOnly - Whether to mark as read-only
 * @returns {Promise<string>} - The new file path
 */
async function copyPatternToWorkspace(sourceFile, workspaceRoot, isReadOnly = false) {
    const patternsDir = path.join(workspaceRoot, 'patterns');
    
    // Ensure patterns directory exists
    if (!fs.existsSync(patternsDir)) {
        fs.mkdirSync(patternsDir, { recursive: true });
    }
    
    const fileName = path.basename(sourceFile);
    let newPath = path.join(patternsDir, fileName);
    
    // Handle name conflicts by appending numbers
    let counter = 1;
    let baseName = fileName.replace('.py', '');
    while (fs.existsSync(newPath)) {
        newPath = path.join(patternsDir, `${baseName}_${counter}.py`);
        counter++;
    }
    
    // Copy the file
    try {
        const content = await fs.promises.readFile(sourceFile, 'utf-8');
        let newContent = content;
        
        if (isReadOnly) {
            // Add a read-only marker comment at the top
            newContent = `# This is a read-only copy from shipped patterns or dependencies.\n# Edit the source pattern or create a new pattern instead.\n\n${content}`;
        }
        
        await fs.promises.writeFile(newPath, newContent, 'utf-8');
        return newPath;
    } catch (error) {
        throw new Error(`Failed to copy pattern: ${error.message}`);
    }
}

/**
 * Duplicates a shipped pattern to the workspace patterns folder.
 * @param {string} sourceFile - The source file path (from dependencies)
 * @param {string} workspaceRoot - The workspace root directory
 * @returns {Promise<string>} - The new file path
 */
async function duplicatePatternToWorkspace(sourceFile, workspaceRoot) {
    return copyPatternToWorkspace(sourceFile, workspaceRoot, false);
}

/**
 * Opens a shipped pattern as a read-only copy in the workspace.
 * @param {string} sourceFile - The source file path (from dependencies)
 * @param {string} workspaceRoot - The workspace root directory
 * @returns {Promise<string>} - The file path that was opened
 */
async function viewShippedPatternSource(sourceFile, workspaceRoot) {
    const readOnlyPath = await copyPatternToWorkspace(sourceFile, workspaceRoot, true);
    return readOnlyPath;
}

/**
 * Extracts patterns from a patternbook file.
 * For now, we group patterns by patternbook name.
 * @param {Array} patterns - Array of pattern items
 * @returns {Map<string, Array>} - Map of patternbook name to patterns
 */
function groupPatternsByPatternbook(patterns) {
    const grouped = new Map();
    
    for (const pattern of patterns) {
        // Assume patterns have a `patternbookName` field or derive it from the file
        const pbName = pattern.patternbookName || getPatternbookName(pattern.sourceFile);
        
        if (!grouped.has(pbName)) {
            grouped.set(pbName, []);
        }
        grouped.get(pbName).push(pattern);
    }
    
    return grouped;
}

module.exports = {
    isPatternbookFile,
    getPatternbookName,
    openFileInEditor,
    copyPatternToWorkspace,
    duplicatePatternToWorkspace,
    viewShippedPatternSource,
    groupPatternsByPatternbook,
};
