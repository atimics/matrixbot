#!/usr/bin/env python3
"""
Payload Analysis Script for Enhanced AI Prompt Logging

This script analyzes dumped payload files to identify optimization opportunities:
- Payload size trends and outliers
- Prompt composition analysis
- Token usage patterns
- Cost optimization suggestions
- System prompt efficiency analysis
"""

import json
import os
import glob
from datetime import datetime
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict
import statistics


@dataclass
class PayloadAnalysis:
    """Analysis results for a single payload"""
    filename: str
    timestamp: str
    cycle_id: str
    model: str
    size_bytes: int
    size_kb: float
    message_count: int
    system_prompt_size: int
    user_prompt_size: int
    tool_count: int
    world_state_size: int
    expansion_utilization: str
    expanded_nodes: int


class PayloadAnalyzer:
    """Analyzes dumped payload files for optimization opportunities"""
    
    def __init__(self, dump_directory: str = "data/payload_dumps"):
        self.dump_directory = dump_directory
        self.analyses: List[PayloadAnalysis] = []
        
    def load_and_analyze_all(self) -> Dict[str, Any]:
        """Load all payload files and perform comprehensive analysis"""
        if not os.path.exists(self.dump_directory):
            print(f"❌ Payload dump directory not found: {self.dump_directory}")
            return {}
            
        payload_files = glob.glob(os.path.join(self.dump_directory, "payload_*.json"))
        if not payload_files:
            print(f"❌ No payload files found in {self.dump_directory}")
            return {}
            
        print(f"📊 Found {len(payload_files)} payload files to analyze")
        
        for filepath in sorted(payload_files):
            try:
                analysis = self._analyze_single_payload(filepath)
                if analysis:
                    self.analyses.append(analysis)
            except Exception as e:
                print(f"⚠️  Error analyzing {filepath}: {e}")
                
        return self._generate_comprehensive_report()
    
    def _analyze_single_payload(self, filepath: str) -> PayloadAnalysis:
        """Analyze a single payload file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        metadata = data.get('metadata', {})
        payload = data.get('payload', {})
        messages = payload.get('messages', [])
        
        # Extract system and user prompt sizes
        system_prompt_size = 0
        user_prompt_size = 0
        
        for msg in messages:
            content_size = len(msg.get('content', '').encode('utf-8'))
            if msg.get('role') == 'system':
                system_prompt_size += content_size
            elif msg.get('role') == 'user':
                user_prompt_size += content_size
                
        # Count tools
        tool_count = len(payload.get('tools', []))
        
        # Analyze world state if present in user message
        world_state_size = 0
        expansion_utilization = "0/0"
        expanded_nodes = 0
        
        for msg in messages:
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                if 'expansion_status' in content:
                    # Extract expansion info from user content
                    try:
                        # Simple regex-like extraction
                        if '"utilization":' in content:
                            start = content.find('"utilization":')
                            end = content.find('"', start + 15)
                            if end > start:
                                expansion_utilization = content[start+15:end].strip(' "')
                        
                        if '"total_expanded":' in content:
                            start = content.find('"total_expanded":')
                            end = content.find(',', start)
                            if end > start:
                                try:
                                    expanded_nodes = int(content[start+17:end].strip())
                                except:
                                    pass
                    except:
                        pass
                        
                world_state_size = len(content.encode('utf-8'))
                
        return PayloadAnalysis(
            filename=os.path.basename(filepath),
            timestamp=metadata.get('timestamp', ''),
            cycle_id=metadata.get('cycle_id', ''),
            model=metadata.get('model', ''),
            size_bytes=metadata.get('payload_size_bytes', 0),
            size_kb=metadata.get('payload_size_kb', 0.0),
            message_count=len(messages),
            system_prompt_size=system_prompt_size,
            user_prompt_size=user_prompt_size,
            tool_count=tool_count,
            world_state_size=world_state_size,
            expansion_utilization=expansion_utilization,
            expanded_nodes=expanded_nodes
        )
    
    def _generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive analysis report"""
        if not self.analyses:
            return {"error": "No valid analyses found"}
            
        report = {
            "summary": self._generate_summary(),
            "size_analysis": self._analyze_sizes(),
            "prompt_composition": self._analyze_prompt_composition(),
            "tool_usage": self._analyze_tool_usage(),
            "world_state_analysis": self._analyze_world_state(),
            "optimization_recommendations": self._generate_recommendations(),
            "trends": self._analyze_trends()
        }
        
        return report
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics"""
        sizes = [a.size_kb for a in self.analyses]
        
        return {
            "total_payloads": len(self.analyses),
            "date_range": {
                "first": self.analyses[0].timestamp if self.analyses else None,
                "last": self.analyses[-1].timestamp if self.analyses else None
            },
            "size_stats_kb": {
                "min": min(sizes) if sizes else 0,
                "max": max(sizes) if sizes else 0,
                "mean": statistics.mean(sizes) if sizes else 0,
                "median": statistics.median(sizes) if sizes else 0,
                "std_dev": statistics.stdev(sizes) if len(sizes) > 1 else 0
            },
            "models_used": list(set(a.model for a in self.analyses))
        }
    
    def _analyze_sizes(self) -> Dict[str, Any]:
        """Analyze payload sizes for optimization opportunities"""
        sizes = [a.size_kb for a in self.analyses]
        mean_size = statistics.mean(sizes) if sizes else 0
        
        # Identify outliers (>2 standard deviations from mean)
        outliers = []
        if len(sizes) > 1:
            std_dev = statistics.stdev(sizes)
            threshold = mean_size + (2 * std_dev)
            outliers = [a for a in self.analyses if a.size_kb > threshold]
        
        return {
            "size_distribution": {
                "small_payloads_under_50kb": len([a for a in self.analyses if a.size_kb < 50]),
                "medium_payloads_50_100kb": len([a for a in self.analyses if 50 <= a.size_kb < 100]),
                "large_payloads_100_200kb": len([a for a in self.analyses if 100 <= a.size_kb < 200]),
                "very_large_payloads_over_200kb": len([a for a in self.analyses if a.size_kb >= 200])
            },
            "outliers": [
                {
                    "filename": a.filename,
                    "size_kb": a.size_kb,
                    "cycle_id": a.cycle_id,
                    "deviation_from_mean": a.size_kb - mean_size
                }
                for a in outliers
            ]
        }
    
    def _analyze_prompt_composition(self) -> Dict[str, Any]:
        """Analyze prompt composition patterns"""
        system_sizes = [a.system_prompt_size for a in self.analyses]
        user_sizes = [a.user_prompt_size for a in self.analyses]
        
        return {
            "system_prompt_stats": {
                "mean_bytes": statistics.mean(system_sizes) if system_sizes else 0,
                "max_bytes": max(system_sizes) if system_sizes else 0,
                "min_bytes": min(system_sizes) if system_sizes else 0,
                "is_consistent": len(set(system_sizes)) == 1
            },
            "user_prompt_stats": {
                "mean_bytes": statistics.mean(user_sizes) if user_sizes else 0,
                "max_bytes": max(user_sizes) if user_sizes else 0,
                "min_bytes": min(user_sizes) if user_sizes else 0,
                "variance": statistics.variance(user_sizes) if len(user_sizes) > 1 else 0
            },
            "composition_ratios": [
                {
                    "filename": a.filename,
                    "system_percent": (a.system_prompt_size / a.size_bytes * 100) if a.size_bytes > 0 else 0,
                    "user_percent": (a.user_prompt_size / a.size_bytes * 100) if a.size_bytes > 0 else 0
                }
                for a in self.analyses
            ]
        }
    
    def _analyze_tool_usage(self) -> Dict[str, Any]:
        """Analyze tool usage patterns"""
        tool_counts = [a.tool_count for a in self.analyses]
        
        return {
            "tool_count_stats": {
                "mean": statistics.mean(tool_counts) if tool_counts else 0,
                "max": max(tool_counts) if tool_counts else 0,
                "min": min(tool_counts) if tool_counts else 0,
                "is_consistent": len(set(tool_counts)) == 1
            },
            "tool_usage_distribution": dict(
                zip(*sorted([(count, tool_counts.count(count)) for count in set(tool_counts)]))
            ) if tool_counts else {}
        }
    
    def _analyze_world_state(self) -> Dict[str, Any]:
        """Analyze world state usage patterns"""
        world_state_sizes = [a.world_state_size for a in self.analyses]
        expanded_nodes = [a.expanded_nodes for a in self.analyses]
        
        return {
            "world_state_size_stats": {
                "mean_bytes": statistics.mean(world_state_sizes) if world_state_sizes else 0,
                "max_bytes": max(world_state_sizes) if world_state_sizes else 0,
                "min_bytes": min(world_state_sizes) if world_state_sizes else 0
            },
            "node_expansion_stats": {
                "mean_expanded": statistics.mean(expanded_nodes) if expanded_nodes else 0,
                "max_expanded": max(expanded_nodes) if expanded_nodes else 0,
                "expansion_utilization_samples": [a.expansion_utilization for a in self.analyses[:10]]
            }
        }
    
    def _analyze_trends(self) -> Dict[str, Any]:
        """Analyze trends over time"""
        if len(self.analyses) < 2:
            return {"note": "Insufficient data for trend analysis"}
            
        # Simple trend analysis
        first_half = self.analyses[:len(self.analyses)//2]
        second_half = self.analyses[len(self.analyses)//2:]
        
        first_avg = statistics.mean([a.size_kb for a in first_half])
        second_avg = statistics.mean([a.size_kb for a in second_half])
        
        return {
            "size_trend": {
                "first_half_avg_kb": first_avg,
                "second_half_avg_kb": second_avg,
                "trend_direction": "increasing" if second_avg > first_avg else "decreasing",
                "change_percent": ((second_avg - first_avg) / first_avg * 100) if first_avg > 0 else 0
            }
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate optimization recommendations based on analysis"""
        recommendations = []
        
        if not self.analyses:
            return ["No data available for recommendations"]
            
        # Size-based recommendations
        sizes = [a.size_kb for a in self.analyses]
        avg_size = statistics.mean(sizes)
        
        if avg_size > 150:
            recommendations.append("🔥 CRITICAL: Average payload size is very large (>150KB). Consider reducing system prompt length or world state data.")
        elif avg_size > 100:
            recommendations.append("⚠️  Average payload size is large (>100KB). Monitor for efficiency improvements.")
            
        # System prompt consistency
        system_sizes = [a.system_prompt_size for a in self.analyses]
        if len(set(system_sizes)) > 1:
            recommendations.append("📝 System prompt size varies across payloads. Ensure consistency for reliable performance.")
            
        # Tool count optimization
        tool_counts = [a.tool_count for a in self.analyses]
        avg_tools = statistics.mean(tool_counts)
        if avg_tools > 50:
            recommendations.append("🛠️  High tool count detected. Consider tool categorization or conditional loading.")
            
        # World state optimization
        world_state_sizes = [a.world_state_size for a in self.analyses]
        avg_world_state = statistics.mean(world_state_sizes)
        total_avg = statistics.mean([a.size_bytes for a in self.analyses])
        
        if avg_world_state / total_avg > 0.7:  # World state is >70% of payload
            recommendations.append("🌍 World state dominates payload size. Consider more aggressive summarization or selective expansion.")
            
        # Expansion utilization
        expanded_counts = [a.expanded_nodes for a in self.analyses]
        avg_expanded = statistics.mean(expanded_counts)
        if avg_expanded < 2:
            recommendations.append("📊 Low node expansion utilization. Consider expanding more relevant nodes for better context.")
        elif avg_expanded > 6:
            recommendations.append("📊 High node expansion utilization. Ensure expanded nodes are necessary for decision making.")
            
        if not recommendations:
            recommendations.append("✅ Payload analysis looks good! No major optimization issues detected.")
            
        return recommendations


def main():
    """Main analysis function"""
    print("🔍 AI Payload Analysis Tool")
    print("=" * 50)
    
    analyzer = PayloadAnalyzer()
    report = analyzer.load_and_analyze_all()
    
    if "error" in report:
        print(f"❌ {report['error']}")
        return
        
    # Print summary
    summary = report['summary']
    print(f"\n📊 ANALYSIS SUMMARY")
    print(f"Total Payloads Analyzed: {summary['total_payloads']}")
    print(f"Models Used: {', '.join(summary['models_used'])}")
    print(f"Size Range: {summary['size_stats_kb']['min']:.1f} - {summary['size_stats_kb']['max']:.1f} KB")
    print(f"Average Size: {summary['size_stats_kb']['mean']:.1f} KB")
    print(f"Median Size: {summary['size_stats_kb']['median']:.1f} KB")
    
    # Print size analysis
    size_analysis = report['size_analysis']
    print(f"\n📏 SIZE DISTRIBUTION")
    dist = size_analysis['size_distribution']
    print(f"Small (<50KB): {dist['small_payloads_under_50kb']}")
    print(f"Medium (50-100KB): {dist['medium_payloads_50_100kb']}")
    print(f"Large (100-200KB): {dist['large_payloads_100_200kb']}")
    print(f"Very Large (>200KB): {dist['very_large_payloads_over_200kb']}")
    
    # Print outliers
    if size_analysis['outliers']:
        print(f"\n🎯 SIZE OUTLIERS")
        for outlier in size_analysis['outliers'][:5]:  # Show top 5
            print(f"  {outlier['filename']}: {outlier['size_kb']:.1f}KB (+{outlier['deviation_from_mean']:.1f}KB from mean)")
    
    # Print prompt composition
    composition = report['prompt_composition']
    print(f"\n📝 PROMPT COMPOSITION")
    print(f"System Prompt: {composition['system_prompt_stats']['mean_bytes']/1024:.1f}KB avg")
    print(f"User Prompt: {composition['user_prompt_stats']['mean_bytes']/1024:.1f}KB avg")
    print(f"System Consistent: {composition['system_prompt_stats']['is_consistent']}")
    
    # Print tool usage
    tools = report['tool_usage']
    print(f"\n🛠️  TOOL USAGE")
    print(f"Average Tools: {tools['tool_count_stats']['mean']:.1f}")
    print(f"Tool Count Range: {tools['tool_count_stats']['min']} - {tools['tool_count_stats']['max']}")
    print(f"Tool Count Consistent: {tools['tool_count_stats']['is_consistent']}")
    
    # Print world state analysis
    world_state = report['world_state_analysis']
    print(f"\n🌍 WORLD STATE ANALYSIS")
    print(f"Average World State Size: {world_state['world_state_size_stats']['mean_bytes']/1024:.1f}KB")
    print(f"Average Expanded Nodes: {world_state['node_expansion_stats']['mean_expanded']:.1f}")
    
    # Print trends
    trends = report['trends']
    if 'size_trend' in trends:
        trend = trends['size_trend']
        print(f"\n📈 TRENDS")
        print(f"Size Trend: {trend['trend_direction']} ({trend['change_percent']:.1f}%)")
        print(f"First Half Avg: {trend['first_half_avg_kb']:.1f}KB")
        print(f"Second Half Avg: {trend['second_half_avg_kb']:.1f}KB")
    
    # Print recommendations
    print(f"\n💡 OPTIMIZATION RECOMMENDATIONS")
    for i, rec in enumerate(report['optimization_recommendations'], 1):
        print(f"{i}. {rec}")
    
    # Save detailed report
    output_file = "payload_analysis_report.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, default=str)
    
    print(f"\n📄 Detailed report saved to: {output_file}")


if __name__ == "__main__":
    main()
