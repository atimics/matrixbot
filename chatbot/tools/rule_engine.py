"""
Pluggable rule engine for code analysis.

This module provides a flexible framework for defining and executing code analysis rules
across different focuses (security, performance, code quality, etc.).
"""
import ast
import re
import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Pattern
from pathlib import Path
from dataclasses import dataclass, field
import logging

from .models import RuleMatch, AnalysisFocus


logger = logging.getLogger(__name__)


class AnalysisRule(ABC):
    """Base class for all code analysis rules."""
    
    def __init__(self, rule_id: str, severity: str = "warning", description: str = ""):
        self.rule_id = rule_id
        self.severity = severity
        self.description = description
        self.enabled = True
    
    @property
    @abstractmethod
    def supported_file_types(self) -> Set[str]:
        """File extensions this rule can analyze (e.g., {'.py', '.js'})."""
        pass
    
    @abstractmethod
    async def analyze_file(self, file_path: Path, content: str) -> List[RuleMatch]:
        """Analyze a file and return any rule matches."""
        pass
    
    def is_applicable(self, file_path: Path) -> bool:
        """Check if this rule applies to the given file."""
        return file_path.suffix.lower() in self.supported_file_types


class RegexRule(AnalysisRule):
    """Rule based on regular expression pattern matching."""
    
    def __init__(
        self, 
        rule_id: str, 
        pattern: str, 
        message: str,
        severity: str = "warning",
        description: str = "",
        supported_extensions: Optional[Set[str]] = None,
        suggested_fix: Optional[str] = None,
        flags: int = re.IGNORECASE
    ):
        super().__init__(rule_id, severity, description)
        self.pattern = re.compile(pattern, flags)
        self.message = message
        self.suggested_fix = suggested_fix
        self._supported_extensions = supported_extensions or {'.py', '.js', '.ts', '.java', '.cpp', '.c'}
    
    @property
    def supported_file_types(self) -> Set[str]:
        return self._supported_extensions
    
    async def analyze_file(self, file_path: Path, content: str) -> List[RuleMatch]:
        matches = []
        lines = content.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            for match in self.pattern.finditer(line):
                rule_match = RuleMatch(
                    rule_id=self.rule_id,
                    file_path=str(file_path),
                    line_number=line_num,
                    column=match.start(),
                    message=self.message.format(match=match.group()),
                    severity=self.severity,
                    suggested_fix=self.suggested_fix,
                    context={"matched_text": match.group(), "line_content": line.strip()}
                )
                matches.append(rule_match)
        
        return matches


class ASTRule(AnalysisRule):
    """Rule based on AST (Abstract Syntax Tree) analysis for Python files."""
    
    def __init__(self, rule_id: str, severity: str = "warning", description: str = ""):
        super().__init__(rule_id, severity, description)
    
    @property
    def supported_file_types(self) -> Set[str]:
        return {'.py'}
    
    async def analyze_file(self, file_path: Path, content: str) -> List[RuleMatch]:
        try:
            tree = ast.parse(content)
            return await self.analyze_ast(file_path, tree, content)
        except SyntaxError as e:
            # Return syntax error as a rule match
            return [RuleMatch(
                rule_id=f"{self.rule_id}_syntax_error",
                file_path=str(file_path),
                line_number=e.lineno or 1,
                column=e.offset,
                message=f"Syntax error: {e.msg}",
                severity="error"
            )]
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return []
    
    @abstractmethod
    async def analyze_ast(self, file_path: Path, tree: ast.AST, content: str) -> List[RuleMatch]:
        """Analyze the AST and return rule matches."""
        pass


class FunctionLengthRule(ASTRule):
    """Rule to detect overly long functions."""
    
    def __init__(self, max_lines: int = 50):
        super().__init__(
            rule_id="function_length", 
            severity="warning",
            description=f"Functions should not exceed {max_lines} lines"
        )
        self.max_lines = max_lines
    
    async def analyze_ast(self, file_path: Path, tree: ast.AST, content: str) -> List[RuleMatch]:
        matches = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start_line = node.lineno
                # Find the last line by checking all child nodes with line numbers
                end_line = start_line
                for child in ast.walk(node):
                    if hasattr(child, 'lineno'):
                        lineno = getattr(child, 'lineno', None)
                        if lineno is not None:
                            end_line = max(end_line, lineno)
                
                length = end_line - start_line + 1
                
                if length > self.max_lines:
                    matches.append(RuleMatch(
                        rule_id=self.rule_id,
                        file_path=str(file_path),
                        line_number=start_line,
                        message=f"Function '{node.name}' is {length} lines long (max: {self.max_lines})",
                        severity=self.severity,
                        suggested_fix=f"Consider breaking down function '{node.name}' into smaller functions",
                        context={"function_name": node.name, "actual_length": length, "max_length": self.max_lines}
                    ))
        
        return matches


class HardcodedSecretsRule(RegexRule):
    """Rule to detect hardcoded secrets and credentials."""
    
    def __init__(self):
        # Common patterns for secrets
        patterns = [
            r'password\s*=\s*["\'][^"\']{4,}["\']',
            r'api[_-]?key\s*=\s*["\'][^"\']{10,}["\']',
            r'secret\s*=\s*["\'][^"\']{8,}["\']',
            r'token\s*=\s*["\'][^"\']{10,}["\']',
            r'["\'][A-Za-z0-9+/]{40,}={0,2}["\']',  # Base64-like strings
        ]
        
        super().__init__(
            rule_id="hardcoded_secrets",
            pattern="|".join(f"({p})" for p in patterns),
            message="Potential hardcoded secret detected: {match}",
            severity="critical",
            description="Hardcoded secrets should be moved to environment variables or secure vaults",
            suggested_fix="Move secret to environment variable or configuration file"
        )


class TODOCommentsRule(RegexRule):
    """Rule to track TODO/FIXME comments."""
    
    def __init__(self):
        super().__init__(
            rule_id="todo_comments",
            pattern=r'#\s*(TODO|FIXME|XXX|HACK)\b.*',
            message="TODO/FIXME comment found: {match}",
            severity="info",
            description="TODO comments should be tracked and eventually resolved",
            suggested_fix="Create GitHub issue or resolve the TODO item"
        )


class EmptyExceptRule(ASTRule):
    """Rule to detect empty except blocks."""
    
    def __init__(self):
        super().__init__(
            rule_id="empty_except",
            severity="warning", 
            description="Empty except blocks should be avoided"
        )
    
    async def analyze_ast(self, file_path: Path, tree: ast.AST, content: str) -> List[RuleMatch]:
        matches = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                # Check if the except body is empty or only contains pass/ellipsis
                if (not node.body or 
                    (len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Expr))) and
                    isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)):
                    
                    matches.append(RuleMatch(
                        rule_id=self.rule_id,
                        file_path=str(file_path),
                        line_number=node.lineno,
                        message="Empty except block should handle or log the exception",
                        severity=self.severity,
                        suggested_fix="Add proper exception handling or logging",
                        context={"exception_type": ast.dump(node.type) if node.type else "all"}
                    ))
        
        return matches


@dataclass
class RuleSet:
    """Collection of rules for a specific analysis focus."""
    name: str
    description: str
    rules: List[AnalysisRule] = field(default_factory=list)
    
    def add_rule(self, rule: AnalysisRule) -> None:
        """Add a rule to this rule set."""
        self.rules.append(rule)
    
    def get_applicable_rules(self, file_path: Path) -> List[AnalysisRule]:
        """Get rules that apply to the given file."""
        return [rule for rule in self.rules if rule.enabled and rule.is_applicable(file_path)]


class RuleEngine:
    """Main engine for running code analysis rules."""
    
    def __init__(self):
        self.rule_sets: Dict[AnalysisFocus, RuleSet] = {}
        self._setup_default_rule_sets()
    
    def _setup_default_rule_sets(self) -> None:
        """Set up default rule sets for each analysis focus."""
        
        # Security rules
        security_rules = RuleSet("Security Analysis", "Rules for detecting security issues")
        security_rules.add_rule(HardcodedSecretsRule())
        security_rules.add_rule(RegexRule(
            rule_id="sql_injection",
            pattern=r'execute\s*\(\s*["\'].*%.*["\']',
            message="Potential SQL injection vulnerability",
            severity="critical",
            supported_extensions={'.py', '.java', '.php'}
        ))
        self.rule_sets[AnalysisFocus.SECURITY] = security_rules
        
        # Code quality rules
        quality_rules = RuleSet("Code Quality", "Rules for code quality and maintainability")
        quality_rules.add_rule(FunctionLengthRule())
        quality_rules.add_rule(EmptyExceptRule())
        quality_rules.add_rule(TODOCommentsRule())
        quality_rules.add_rule(RegexRule(
            rule_id="long_lines",
            pattern=r'^.{120,}$',
            message="Line exceeds 120 characters",
            severity="info",
            description="Long lines can be harder to read"
        ))
        self.rule_sets[AnalysisFocus.CODE_QUALITY] = quality_rules
        
        # Performance rules
        performance_rules = RuleSet("Performance", "Rules for detecting performance issues")
        performance_rules.add_rule(RegexRule(
            rule_id="inefficient_loop",
            pattern=r'for\s+\w+\s+in\s+range\s*\(\s*len\s*\(',
            message="Consider using enumerate() instead of range(len())",
            severity="info",
            supported_extensions={'.py'},
            suggested_fix="Use enumerate() for better performance and readability"
        ))
        self.rule_sets[AnalysisFocus.PERFORMANCE] = performance_rules
        
        # Documentation rules
        docs_rules = RuleSet("Documentation", "Rules for documentation quality")
        docs_rules.add_rule(RegexRule(
            rule_id="missing_docstring",
            pattern=r'^(class|def|async def)\s+\w+.*:\s*$',
            message="Missing docstring for class/function",
            severity="info",
            supported_extensions={'.py'},
            suggested_fix="Add docstring describing the purpose and parameters"
        ))
        self.rule_sets[AnalysisFocus.DOCUMENTATION] = docs_rules
    
    def get_rule_set(self, focus: AnalysisFocus) -> Optional[RuleSet]:
        """Get the rule set for a specific analysis focus."""
        return self.rule_sets.get(focus)
    
    def add_custom_rule(self, focus: AnalysisFocus, rule: AnalysisRule) -> None:
        """Add a custom rule to a specific focus area."""
        if focus not in self.rule_sets:
            self.rule_sets[focus] = RuleSet(f"Custom {focus.value}", f"Custom rules for {focus.value}")
        
        self.rule_sets[focus].add_rule(rule)
    
    async def analyze_file(
        self, 
        file_path: Path, 
        content: str, 
        focus: AnalysisFocus,
        max_concurrent_rules: int = 10
    ) -> List[RuleMatch]:
        """Analyze a single file with the rules for the given focus."""
        rule_set = self.get_rule_set(focus)
        if not rule_set:
            return []
        
        applicable_rules = rule_set.get_applicable_rules(file_path)
        if not applicable_rules:
            return []
        
        # Run rules concurrently with semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent_rules)
        
        async def run_rule(rule: AnalysisRule) -> List[RuleMatch]:
            async with semaphore:
                try:
                    return await rule.analyze_file(file_path, content)
                except Exception as e:
                    logger.exception(f"Error running rule {rule.rule_id} on {file_path}: {e}")
                    return []
        
        # Execute all applicable rules concurrently
        rule_tasks = [run_rule(rule) for rule in applicable_rules]
        results = await asyncio.gather(*rule_tasks, return_exceptions=True)
        
        # Flatten results and filter out exceptions
        matches = []
        for result in results:
            if isinstance(result, list):
                matches.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Rule execution failed: {result}")
        
        return matches
    
    async def analyze_files(
        self,
        file_paths: List[Path],
        focus: AnalysisFocus,
        max_concurrent_files: int = 5
    ) -> Dict[str, List[RuleMatch]]:
        """Analyze multiple files concurrently."""
        semaphore = asyncio.Semaphore(max_concurrent_files)
        
        async def analyze_single_file(file_path: Path) -> tuple[str, List[RuleMatch]]:
            async with semaphore:
                try:
                    content = file_path.read_text(encoding='utf-8')
                    matches = await self.analyze_file(file_path, content, focus)
                    return str(file_path), matches
                except Exception as e:
                    logger.exception(f"Error analyzing file {file_path}: {e}")
                    return str(file_path), []
        
        # Filter files that are too large or binary
        valid_files = [
            fp for fp in file_paths 
            if fp.is_file() and fp.stat().st_size < 1_000_000  # Max 1MB
        ]
        
        # Execute analysis tasks concurrently
        tasks = [analyze_single_file(fp) for fp in valid_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build results dictionary
        file_matches = {}
        for result in results:
            if isinstance(result, tuple):
                file_path, matches = result
                file_matches[file_path] = matches
            elif isinstance(result, Exception):
                logger.error(f"File analysis failed: {result}")
        
        return file_matches
