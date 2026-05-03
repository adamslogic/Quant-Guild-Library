import os
import argparse
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from agent_utils.notebook_parser import analyze_notebook, search_notebook
from agent_utils.executor import execute_notebook

console = Console()

def get_all_notebooks(root_dir):
    """Recursively find all .ipynb files in a directory."""
    notebooks = []
    for dirpath, _, filenames in os.walk(root_dir):
        # skip hidden dirs or git or python cache
        if '.git' in dirpath or '__pycache__' in dirpath or '.ipynb_checkpoints' in dirpath:
            continue
        for f in filenames:
            if f.endswith('.ipynb'):
                notebooks.append(os.path.join(dirpath, f))
    return notebooks

def list_notebooks():
    """Lists all notebooks in the repository."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    notebooks = get_all_notebooks(root_dir)
    
    table = Table(title=f"Jupyter Notebooks in Quant Guild Library ({len(notebooks)} found)")
    table.add_column("Index", style="cyan", width=5)
    table.add_column("Notebook Path", style="green")
    
    for i, nb in enumerate(sorted(notebooks), 1):
        rel_path = os.path.relpath(nb, root_dir)
        table.add_row(str(i), rel_path)
        
    console.print(table)

def analyze(filepath):
    """Analyzes a specific notebook."""
    if not os.path.exists(filepath):
        console.print(f"[red]Error: File {filepath} not found.[/red]")
        return
    
    with console.status(f"Analyzing {filepath}..."):
        stats = analyze_notebook(filepath)
        
    if stats.get("error"):
        console.print(f"[red]{stats['error']}[/red]")
        return
        
    # Print stats
    console.print(Panel(f"[bold blue]Analysis for:[/bold blue] {filepath}", expand=False))
    console.print(f"[bold]Total Cells:[/bold] {stats['total_cells']} (Code: {stats['code_cells']}, Markdown: {stats['markdown_cells']})")
    
    if stats['imports']:
        console.print("[bold]Imports:[/bold] " + ", ".join(stats['imports']))
    else:
        console.print("[bold]Imports:[/bold] None found")
        
    if stats['defined_functions']:
        console.print("[bold]Functions Defined:[/bold] " + ", ".join(stats['defined_functions']))
        
    if stats['defined_classes']:
        console.print("[bold]Classes Defined:[/bold] " + ", ".join(stats['defined_classes']))

def search(query):
    """Searches all notebooks for a given query string."""
    root_dir = os.path.dirname(os.path.abspath(__file__))
    notebooks = get_all_notebooks(root_dir)
    
    found_any = False
    
    with console.status(f"Searching {len(notebooks)} notebooks for '{query}'..."):
        for nb in notebooks:
            results = search_notebook(nb, query)
            if results:
                found_any = True
                rel_path = os.path.relpath(nb, root_dir)
                console.print(f"\n[bold yellow]Found in:[/bold yellow] {rel_path}")
                for res in results:
                    console.print(f"  [cyan]Cell {res['cell_index']} ({res['cell_type']}):[/cyan]")
                    # Highlight the query if possible by simple text replace or just print
                    snippet = res['source_snippet']
                    # Print as syntax if code, else plain
                    if res['cell_type'] == 'code':
                        syntax = Syntax(snippet, "python", theme="monokai", line_numbers=False)
                        console.print(syntax)
                    else:
                        console.print(f"    {snippet.replace(query, f'[bold red]{query}[/bold red]')}")
                        
    if not found_any:
        console.print(f"[yellow]No results found for query '{query}'.[/yellow]")

def execute(filepath):
    """Executes a notebook."""
    if not os.path.exists(filepath):
        console.print(f"[red]Error: File {filepath} not found.[/red]")
        return
        
    console.print(f"[bold yellow]Executing Notebook:[/bold yellow] {filepath}")
    console.print("This might take a while depending on the complexity of the code...")
    
    with console.status("Executing...", spinner="dots"):
        success, out_path, error = execute_notebook(filepath)
        
    if success:
        console.print(f"[bold green]Success![/bold green] Executed notebook saved to: {out_path}")
    else:
        console.print(f"[bold red]Execution Failed![/bold red] Saved partial output to: {out_path}")
        console.print(f"Error Details:\n{error}")

def main():
    parser = argparse.ArgumentParser(description="Quant Guild Library Repository Explorer")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List command
    subparsers.add_parser("list", help="List all Jupyter Notebooks in the repository")
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze a specific notebook")
    analyze_parser.add_argument("filepath", type=str, help="Path to the .ipynb file")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search across all notebooks")
    search_parser.add_argument("query", type=str, help="Text to search for")
    
    # Execute command
    execute_parser = subparsers.add_parser("execute", help="Programmatically execute a notebook")
    execute_parser.add_argument("filepath", type=str, help="Path to the .ipynb file to execute")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_notebooks()
    elif args.command == "analyze":
        analyze(args.filepath)
    elif args.command == "search":
        search(args.query)
    elif args.command == "execute":
        execute(args.filepath)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
