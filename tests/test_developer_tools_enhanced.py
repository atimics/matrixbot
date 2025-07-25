"""
Test suite for the developer tools system including models and rule engine.

This test suite covers:
- ChangeSpec model serialization/deserialization
- RuleEngine functionality
- Integration between analysis and implementation
"""
import pytest
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

from chatbot.tools.models import (
    ChangeSpec, ChangeType, Priority, AnalysisFocus, 
    AnalysisResult, RuleMatch, DiffHunk
)
from chatbot.tools.rule_engine import (
    RuleEngine, RegexRule, ASTRule, FunctionLengthRule,
    HardcodedSecretsRule, TODOCommentsRule, EmptyExceptRule
)
from chatbot.tools.developer_tools import AnalyzeAndProposeChangeTool
from chatbot.tools.base import ActionContext


class TestChangeSpecModel:
    """Test the ChangeSpec model functionality."""
    
    def test_change_spec_creation(self):
        """Test creating a ChangeSpec with basic properties."""
        change = ChangeSpec(
            title="Fix import order",
            description="Reorganize imports according to PEP8",
            change_type=ChangeType.MODIFY,
            priority=Priority.LOW,
            file_path="src/module.py"
        )
        
        assert change.title == "Fix import order"
        assert change.change_type == ChangeType.MODIFY
        assert change.priority == Priority.LOW
        assert change.file_path == "src/module.py"
        assert not change.implemented
    
    def test_change_spec_with_diff_hunks(self):
        """Test ChangeSpec with diff hunks."""
        change = ChangeSpec(
            title="Fix function",
            file_path="test.py"
        )
        
        change.add_diff_hunk(
            start_line=10,
            end_line=12,
            old_content="old code",
            new_content="new code",
            context_before=["# context before"],
            context_after=["# context after"]
        )
        
        assert len(change.diff_hunks) == 1
        hunk = change.diff_hunks[0]
        assert hunk.start_line == 10
        assert hunk.end_line == 12
        assert hunk.old_content == "old code"
        assert hunk.new_content == "new code"
    
    def test_change_spec_serialization(self):
        """Test ChangeSpec to_dict and from_dict methods."""
        original = ChangeSpec(
            title="Test change",
            description="Test description",
            change_type=ChangeType.CREATE,
            priority=Priority.HIGH,
            file_path="new_file.py",
            rationale="Testing serialization"
        )
        
        original.add_diff_hunk(5, 7, "old", "new")
        
        # Serialize
        data = original.to_dict()
        
        # Deserialize
        restored = ChangeSpec.from_dict(data)
        
        assert restored.title == original.title
        assert restored.description == original.description
        assert restored.change_type == original.change_type
        assert restored.priority == original.priority
        assert restored.file_path == original.file_path
        assert restored.rationale == original.rationale
        assert len(restored.diff_hunks) == len(original.diff_hunks)
    
    def test_diff_hunk_unified_format(self):
        """Test DiffHunk unified diff output."""
        hunk = DiffHunk(
            file_path="test.py",
            start_line=5,
            end_line=7,
            old_content="old line",
            new_content="new line",
            context_lines_before=["context before"],
            context_lines_after=["context after"]
        )
        
        unified = hunk.to_unified_diff()
        assert " context before" in unified
        assert "-old line" in unified
        assert "+new line" in unified
        assert " context after" in unified


class TestRuleEngine:
    """Test the RuleEngine and individual rules."""
    
    def test_regex_rule_basic(self):
        """Test basic regex rule functionality."""
        rule = RegexRule(
            rule_id="test_rule",
            pattern=r"TODO.*",
            message="TODO found: {match}",
            severity="info"
        )
        
        assert rule.rule_id == "test_rule"
        assert rule.severity == "info"
        assert ".py" in rule.supported_file_types
    
    @pytest.mark.asyncio
    async def test_regex_rule_analysis(self):
        """Test regex rule analysis of file content."""
        rule = TODOCommentsRule()
        
        content = """
def function():
    # TODO: Fix this function
    pass
    
def another():
    # FIXME: Needs improvement
    return None
"""
        
        matches = await rule.analyze_file(Path("test.py"), content)
        
        assert len(matches) == 2
        assert matches[0].rule_id == "todo_comments"
        assert matches[0].line_number == 3
        assert "TODO" in matches[0].message
        assert matches[1].line_number == 7
        assert "FIXME" in matches[1].message
    
    @pytest.mark.asyncio
    async def test_hardcoded_secrets_rule(self):
        """Test hardcoded secrets detection."""
        rule = HardcodedSecretsRule()
        
        content = '''
API_KEY = "sk-1234567890abcdef"
password = "mypassword123"
normal_var = "hello"
'''
        
        matches = await rule.analyze_file(Path("config.py"), content)
        
        # Should detect the API key and password
        assert len(matches) >= 1
        assert any("secret" in match.message.lower() or "password" in match.message.lower() 
                  for match in matches)
    
    @pytest.mark.asyncio
    async def test_function_length_rule(self):
        """Test function length analysis rule."""
        rule = FunctionLengthRule(max_lines=5)
        
        # Create a long function
        content = """
def long_function():
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    return line7

def short_function():
    return 42
"""
        
        matches = await rule.analyze_file(Path("test.py"), content)
        
        # Should flag the long function but not the short one
        assert len(matches) == 1
        assert "long_function" in matches[0].message
        assert matches[0].severity == "warning"
    
    @pytest.mark.asyncio
    async def test_empty_except_rule(self):
        """Test empty except block detection."""
        rule = EmptyExceptRule()
        
        content = """
try:
    risky_operation()
except:
    pass

try:
    another_operation()
except Exception as e:
    logger.error(f"Error: {e}")
"""
        
        matches = await rule.analyze_file(Path("test.py"), content)
        
        # Should only flag the empty except block
        assert len(matches) == 1
        assert matches[0].line_number == 4  # The except line
    
    def test_rule_engine_initialization(self):
        """Test RuleEngine initialization with default rule sets."""
        engine = RuleEngine()
        
        # Should have rule sets for all analysis focuses
        assert AnalysisFocus.SECURITY in engine.rule_sets
        assert AnalysisFocus.CODE_QUALITY in engine.rule_sets
        assert AnalysisFocus.PERFORMANCE in engine.rule_sets
        assert AnalysisFocus.DOCUMENTATION in engine.rule_sets
        
        # Rule sets should have rules
        security_rules = engine.get_rule_set(AnalysisFocus.SECURITY)
        assert security_rules is not None
        assert len(security_rules.rules) > 0
    
    @pytest.mark.asyncio
    async def test_rule_engine_file_analysis(self):
        """Test RuleEngine analyzing a single file."""
        engine = RuleEngine()
        
        content = """
def function():
    # TODO: Implement this
    password = "hardcoded_secret"
    pass
"""
        
        matches = await engine.analyze_file(
            Path("test.py"), 
            content, 
            AnalysisFocus.SECURITY
        )
        
        # Should find security issues
        assert len(matches) > 0
        rule_ids = [match.rule_id for match in matches]
        assert any("secret" in rule_id or "password" in rule_id for rule_id in rule_ids)
    
    @pytest.mark.asyncio
    async def test_rule_engine_multiple_files(self):
        """Test RuleEngine analyzing multiple files concurrently."""
        engine = RuleEngine()
        
        # Create temporary files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # File 1 with TODO
            file1 = temp_path / "file1.py"
            file1.write_text("# TODO: Fix this\ndef func(): pass")
            
            # File 2 with long function
            file2 = temp_path / "file2.py"
            file2.write_text("""
def long_function():
    # Many lines here
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    return line7
""")
            
            file_matches = await engine.analyze_files(
                [file1, file2],
                AnalysisFocus.CODE_QUALITY,
                max_concurrent_files=2
            )
            
            assert len(file_matches) == 2
            assert str(file1) in file_matches
            assert str(file2) in file_matches
            
            # Both files should have some matches
            total_matches = sum(len(matches) for matches in file_matches.values())
            assert total_matches > 0


class TestAnalysisResult:
    """Test the AnalysisResult model."""
    
    def test_analysis_result_creation(self):
        """Test creating and populating AnalysisResult."""
        result = AnalysisResult(
            focus=AnalysisFocus.CODE_QUALITY,
            workspace_path="/test/workspace"
        )
        
        result.add_issue("file.py", 10, "error", "Test issue", "test_rule")
        result.add_opportunity("file.py", "Test opportunity", "high")
        
        assert result.focus == AnalysisFocus.CODE_QUALITY
        assert len(result.issues_found) == 1
        assert len(result.opportunities) == 1
        
        issue = result.issues_found[0]
        assert issue["file_path"] == "file.py"
        assert issue["line"] == 10
        assert issue["severity"] == "error"
        assert issue["rule_id"] == "test_rule"
        
        opportunity = result.opportunities[0]
        assert opportunity["file_path"] == "file.py"
        assert opportunity["impact"] == "high"
    
    def test_analysis_result_summary(self):
        """Test AnalysisResult summary generation."""
        result = AnalysisResult(
            focus=AnalysisFocus.SECURITY,
            workspace_path="/test"
        )
        
        result.files_analyzed = ["file1.py", "file2.py"]
        result.add_issue("file1.py", 5, "critical", "Security issue")
        result.add_opportunity("file2.py", "Security improvement")
        result.analysis_time = 1.5
        
        summary = result.get_summary()
        
        assert summary["focus"] == "security"
        assert summary["files_analyzed_count"] == 2
        assert summary["issues_count"] == 1
        assert summary["opportunities_count"] == 1
        assert summary["analysis_time"] == 1.5


class TestRuleMatch:
    """Test the RuleMatch model."""
    
    def test_rule_match_to_change_spec(self):
        """Test converting RuleMatch to ChangeSpec."""
        rule_match = RuleMatch(
            rule_id="test_rule",
            file_path="test.py",
            line_number=10,
            message="Test issue found",
            severity="warning",
            suggested_fix="Apply this fix"
        )
        
        change_spec = rule_match.to_change_spec("Custom title")
        
        assert change_spec is not None
        assert change_spec.title == "Custom title"
        assert change_spec.description == "Test issue found"
        assert change_spec.file_path == "test.py"
        assert change_spec.priority == Priority.MEDIUM  # warning -> medium
        assert "test_rule" in change_spec.tags
        assert "warning" in change_spec.tags
    
    def test_rule_match_without_fix(self):
        """Test RuleMatch without suggested fix doesn't create ChangeSpec."""
        rule_match = RuleMatch(
            rule_id="test_rule",
            file_path="test.py",
            line_number=10,
            message="Issue without fix"
        )
        
        change_spec = rule_match.to_change_spec()
        
        assert change_spec is None


class TestDeveloperToolsIntegration:
    """Test integration between components."""
    
    @pytest.mark.asyncio
    async def test_analyze_and_propose_change_tool_basic(self):
        """Test basic functionality of AnalyzeAndProposeChangeTool."""
        # Create mock context
        context = Mock(spec=ActionContext)
        context.world_state_manager = None  # Simulating no world state
        
        tool = AnalyzeAndProposeChangeTool()
        
        # Test parameter schema
        schema = tool.parameters_schema
        assert "target_repo_url" in schema
        assert "focus" in schema
        
        # Test basic properties
        assert tool.name == "AnalyzeAndProposeChange"
        assert "analyze" in tool.description.lower()
    
    def test_change_spec_integration_with_priority_mapping(self):
        """Test that rule severity correctly maps to ChangeSpec priority."""
        # Critical rule match should create high priority change
        critical_match = RuleMatch(
            rule_id="critical_rule",
            file_path="test.py",
            line_number=1,
            severity="critical",
            suggested_fix="Fix critical issue"
        )
        
        change_spec = critical_match.to_change_spec()
        assert change_spec is not None
        assert change_spec.priority == Priority.HIGH
        
        # Warning should create medium priority
        warning_match = RuleMatch(
            rule_id="warning_rule", 
            file_path="test.py",
            line_number=1,
            severity="warning",
            suggested_fix="Fix warning"
        )
        
        change_spec = warning_match.to_change_spec()
        assert change_spec is not None
        assert change_spec.priority == Priority.MEDIUM


@pytest.mark.asyncio
async def test_concurrent_analysis_performance():
    """Test that concurrent analysis provides performance benefits."""
    import time
    
    engine = RuleEngine()
    
    # Create test content that will trigger rules
    test_content = """
# TODO: This needs optimization
def very_long_function():
    password = "hardcoded123"
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    line9 = 9
    line10 = 10
    return line10
"""
    
    # Create multiple test files
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        files = []
        
        for i in range(5):
            file_path = temp_path / f"test_{i}.py"
            file_path.write_text(test_content)
            files.append(file_path)
        
        # Test concurrent analysis
        start_time = time.time()
        results = await engine.analyze_files(
            files,
            AnalysisFocus.CODE_QUALITY,
            max_concurrent_files=3
        )
        concurrent_time = time.time() - start_time
        
        # Verify results
        assert len(results) == 5
        for file_path in files:
            assert str(file_path) in results
            # Each file should have some matches
            assert len(results[str(file_path)]) > 0
        
        # Test should complete in reasonable time (less than 2 seconds for 5 small files)
        assert concurrent_time < 2.0, f"Analysis took too long: {concurrent_time}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
