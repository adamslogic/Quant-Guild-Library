import nbformat
import ast

def load_notebook(filepath):
    """Loads a notebook and returns the nbformat notebook node object."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            nb = nbformat.read(f, as_version=4)
        return nb
    except Exception as e:
        return None

def analyze_notebook(filepath):
    """
    Parses a notebook and returns a dictionary with:
    - total_cells: int
    - code_cells: int
    - markdown_cells: int
    - imports: list of str
    - defined_functions: list of str
    - defined_classes: list of str
    """
    nb = load_notebook(filepath)
    if not nb:
        return {"error": "Failed to parse notebook or file not found."}

    stats = {
        "total_cells": len(nb.cells),
        "code_cells": 0,
        "markdown_cells": 0,
        "imports": set(),
        "defined_functions": set(),
        "defined_classes": set(),
        "error": None
    }

    for cell in nb.cells:
        if cell.cell_type == 'markdown':
            stats["markdown_cells"] += 1
        elif cell.cell_type == 'code':
            stats["code_cells"] += 1
            source = cell.source
            # Try to parse AST
            try:
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            stats["imports"].add(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            stats["imports"].add(node.module)
                    elif isinstance(node, ast.FunctionDef):
                        stats["defined_functions"].add(node.name)
                    elif isinstance(node, ast.ClassDef):
                        stats["defined_classes"].add(node.name)
            except SyntaxError:
                # Magic commands like %matplotlib inline will cause SyntaxError
                # We could filter them out, but for simplicity, we skip AST parsing for cells with magic commands
                pass

    stats["imports"] = sorted(list(stats["imports"]))
    stats["defined_functions"] = sorted(list(stats["defined_functions"]))
    stats["defined_classes"] = sorted(list(stats["defined_classes"]))
    
    return stats

def search_notebook(filepath, query):
    """
    Searches a notebook for a given string query.
    Returns a list of dictionaries with cell type and source snippet.
    """
    nb = load_notebook(filepath)
    if not nb:
        return []

    results = []
    query_lower = query.lower()
    for idx, cell in enumerate(nb.cells):
        source = cell.source
        if query_lower in source.lower():
            results.append({
                "cell_index": idx,
                "cell_type": cell.cell_type,
                "source_snippet": source[:200] + "..." if len(source) > 200 else source
            })
    return results

def extract_knowledge(filepath):
    """
    Extracts all markdown text and code source from a notebook for distillation.
    Returns a formatted string containing the notebook's core content.
    """
    nb = load_notebook(filepath)
    if not nb:
        return ""

    extracted = []
    extracted.append(f"=== NOTEBOOK: {filepath} ===")
    
    for idx, cell in enumerate(nb.cells):
        if cell.cell_type == 'markdown':
            extracted.append(f"\n--- [Markdown Cell {idx}] ---")
            extracted.append(cell.source)
        elif cell.cell_type == 'code':
            # Just extract the raw code for distillation, or maybe just docstrings/functions if it's too long
            # To keep it compact, we will extract the whole code cell but only if it's not too long
            source = cell.source.strip()
            if source:
                extracted.append(f"\n--- [Code Cell {idx}] ---")
                extracted.append(source)
                
    return "\n".join(extracted)

