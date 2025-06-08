"""
Tests for Matrix markdown formatting functionality.
"""
import pytest
from chatbot.utils.markdown_utils import format_for_matrix, MatrixMarkdownFormatter


class TestMarkdownFormatting:
    
    def test_basic_formatting(self):
        """Test basic markdown formatting conversion."""
        content = "**Bold text** and *italic text*"
        result = format_for_matrix(content)
        
        assert "Bold text" in result["plain"]
        assert "italic text" in result["plain"]
        assert "<strong>Bold text</strong>" in result["html"]
        assert "<em>italic text</em>" in result["html"]
    
    def test_code_blocks(self):
        """Test that code blocks are formatted correctly."""
        markdown_text = "Here's some code:\n```python\ndef hello():\n    print(\"Hello, World!\")\n```"
        result = format_for_matrix(markdown_text)
        assert 'class="codehilite"' in result["html"]
        assert "<pre>" in result["html"]
        assert "<code>" in result["html"]
        assert "def hello():" in result["html"]

    def test_inline_code(self):
        """Test inline code formatting."""
        content = "Use the `print()` function"
        result = format_for_matrix(content)
        
        assert "print()" in result["plain"]
        assert "<code>print()</code>" in result["html"]
    
    def test_links(self):
        """Test link formatting."""
        content = "Check out [Google](https://google.com)"
        result = format_for_matrix(content)
        
        assert "Google" in result["plain"]
        assert "https://google.com" not in result["plain"]
        assert 'href="https://google.com"' in result["html"]
    
    def test_headers(self):
        """Test header formatting."""
        content = """
# Main Header
## Sub Header
Some content here
"""
        result = format_for_matrix(content)
        
        assert "Main Header" in result["plain"]
        assert "Sub Header" in result["plain"]
        assert "#" not in result["plain"]
        assert "<h1>Main Header</h1>" in result["html"]
        assert "<h2>Sub Header</h2>" in result["html"]
    
    def test_lists(self):
        """Test list formatting."""
        content = """
- Item 1
- Item 2
- Item 3
"""
        result = format_for_matrix(content)
        
        assert "Item 1" in result["plain"]
        assert "<ul>" in result["html"]
        assert "<li>Item 1</li>" in result["html"]
    
    def test_numbered_lists(self):
        """Test numbered list formatting."""
        content = """
1. First item
2. Second item
3. Third item
"""
        result = format_for_matrix(content)
        
        assert "First item" in result["plain"]
        assert "<ol>" in result["html"]
        assert "<li>First item</li>" in result["html"]
    
    def test_mixed_formatting(self):
        """Test a mix of all formatting options."""
        markdown_text = """# AI Response

Here's what I found:

- **Important**: This is critical
- *Note*: Check the `config.json` file
- See [documentation](https://example.com) for details

```python
# Example code
def process_data():
    return {"status": "success"}
```

Thanks!"""
        result = format_for_matrix(markdown_text)
        assert 'class="codehilite"' in result["html"]
        assert "<h1>AI Response</h1>" in result["html"]
        assert "<strong>Important</strong>" in result["html"]
        assert "<em>Note</em>" in result["html"]
        assert 'href="https://example.com"' in result["html"]
        assert "def process_data():" in result["html"]


class TestMatrixMarkdownFormatter:
    
    def test_formatter_instance(self):
        """Test that formatter can be instantiated."""
        formatter = MatrixMarkdownFormatter()
        assert formatter is not None
        assert formatter.md is not None
    
    def test_plain_text_cleaning(self):
        """Test that plain text conversion removes markdown syntax properly."""
        formatter = MatrixMarkdownFormatter()
        
        # Test various markdown elements
        test_cases = [
            ("**bold**", "bold"),
            ("*italic*", "italic"),
            ("`code`", "code"),
            ("# Header", "Header"),
            ("- List item", "List item"),
            ("1. Numbered item", "Numbered item"),
            ("[Link text](http://example.com)", "Link text"),
        ]
        
        for markdown_input, expected_plain in test_cases:
            result = formatter._markdown_to_plain(markdown_input)
            assert expected_plain in result
            assert "**" not in result
            assert "*" not in result or expected_plain == "List item"  # Allow asterisk in expected output
            assert "`" not in result
            assert "#" not in result
            assert "[" not in result
            assert "]" not in result
            assert "(" not in result
            assert ")" not in result
