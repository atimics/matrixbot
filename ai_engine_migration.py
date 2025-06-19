#!/usr/bin/env python3
"""
AI Engine Migration Script

This script helps migrate from legacy AI engine usage to the unified AIEngine.
It analyzes the codebase and provides recommendations for updates.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Dict, Tuple

class AIEngineMigrationAnalyzer:
    """Analyzes codebase for AI engine usage patterns."""
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)
        self.issues = []
        self.recommendations = []
    
    def analyze(self) -> Dict[str, List[str]]:
        """Perform comprehensive analysis of AI engine usage."""
        print("🔍 Analyzing AI engine usage patterns...")
        
        # Find all Python files
        python_files = list(self.root_path.rglob("*.py"))
        
        for file_path in python_files:
            if self._should_skip_file(file_path):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                self._analyze_file(file_path, content)
            except Exception as e:
                print(f"⚠️  Error reading {file_path}: {e}")
        
        return self._generate_report()
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped."""
        skip_patterns = [
            '__pycache__',
            '.venv',
            'node_modules',
            '.git',
            'migrations',
        ]
        
        return any(pattern in str(file_path) for pattern in skip_patterns)
    
    def _analyze_file(self, file_path: Path, content: str):
        """Analyze a single file for AI engine usage."""
        relative_path = file_path.relative_to(self.root_path)
        
        # Check for legacy imports
        legacy_imports = [
            r'from.*ai_engine import.*AIDecisionEngine',
            r'from.*ai_engine_v2 import.*AIEngineV2',
            r'from.*ai_engine_v2 import.*EnhancedAIEngine',
            r'from.*ai_engine_v2 import.*LegacyAIEngineAdapter',
        ]
        
        for pattern in legacy_imports:
            if re.search(pattern, content):
                self.issues.append(f"📦 {relative_path}: Uses legacy import pattern")
                self.recommendations.append(
                    f"   → Update to: from chatbot.core.ai_engine_v2 import AIEngine"
                )
        
        # Check for legacy constructors
        legacy_constructors = [
            r'AIDecisionEngine\(',
            r'AIEngineV2\(',
            r'EnhancedAIEngine\(',
            r'LegacyAIEngineAdapter\(',
        ]
        
        for pattern in legacy_constructors:
            if re.search(pattern, content):
                self.issues.append(f"🏗️  {relative_path}: Uses legacy constructor")
                self.recommendations.append(
                    f"   → Update to: AIEngine(...)"
                )
        
        # Check for deprecated factory functions
        if re.search(r'create_enhanced_ai_engine\(', content):
            self.issues.append(f"🏭 {relative_path}: Uses deprecated factory function")
            self.recommendations.append(
                f"   → Update to: create_ai_engine(...)"
            )
        
        # Check for legacy method calls
        legacy_methods = [
            r'\.decide_actions\(',
            r'\.generate_response\(',
        ]
        
        for pattern in legacy_methods:
            if re.search(pattern, content):
                self.issues.append(f"🔧 {relative_path}: Uses legacy method interface")
                self.recommendations.append(
                    f"   → Consider migrating to: .generate_structured_response(...)"
                )
    
    def _generate_report(self) -> Dict[str, List[str]]:
        """Generate migration report."""
        return {
            'issues': self.issues,
            'recommendations': self.recommendations,
            'summary': self._generate_summary()
        }
    
    def _generate_summary(self) -> List[str]:
        """Generate summary of findings."""
        summary = [
            f"📊 Analysis Summary:",
            f"   • Found {len(self.issues)} migration opportunities",
            f"   • Legacy imports should be updated to use AIEngine",
            f"   • Legacy constructors should use unified interface",
            f"   • Consider using structured response methods for new code",
            "",
            "🎯 Priority Actions:",
            "   1. Update imports to use AIEngine from ai_engine_v2",
            "   2. Replace legacy constructors with AIEngine(...)",
            "   3. Update factory function calls to create_ai_engine()",
            "   4. Test existing functionality after migration",
            "",
            "✅ Benefits of Migration:",
            "   • Unified interface reduces complexity",
            "   • Better error handling and structured outputs", 
            "   • Future-proofed for new AI features",
            "   • Maintains backward compatibility during transition",
        ]
        
        return summary


def main():
    """Main migration analysis function."""
    if len(sys.argv) != 2:
        print("Usage: python ai_engine_migration.py <project_root>")
        sys.exit(1)
    
    project_root = sys.argv[1]
    if not os.path.exists(project_root):
        print(f"❌ Project root not found: {project_root}")
        sys.exit(1)
    
    print("🚀 AI Engine Migration Analysis")
    print("="*50)
    
    analyzer = AIEngineMigrationAnalyzer(project_root)
    report = analyzer.analyze()
    
    # Print issues
    if report['issues']:
        print("\n🔍 Issues Found:")
        for issue in report['issues']:
            print(f"  {issue}")
    
    # Print recommendations  
    if report['recommendations']:
        print("\n💡 Recommendations:")
        for rec in report['recommendations']:
            print(f"  {rec}")
    
    # Print summary
    print("\n" + "="*50)
    for line in report['summary']:
        print(line)
    
    print("\n✨ Migration analysis complete!")


if __name__ == "__main__":
    main()
