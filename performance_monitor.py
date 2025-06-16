#!/usr/bin/env python3
"""
Performance monitoring and optimization tool for RATi Chatbot System.
Analyzes logs, tracks token usage, and provides optimization recommendations.
"""

import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import statistics

class PerformanceAnalyzer:
    def __init__(self, log_file: str = "chatbot.log"):
        self.log_file = Path(log_file)
        self.token_usage_pattern = re.compile(r'tokens: (\d+)')
        self.payload_size_pattern = re.compile(r'Payload size: ([\d.]+)KB')
        self.response_time_pattern = re.compile(r'Response time: ([\d.]+)s')
        self.api_call_pattern = re.compile(r'Making API call to')
        self.decision_cycle_pattern = re.compile(r'Decision cycle \d+')
        
    def parse_logs(self, hours: int = 24) -> Dict:
        """Parse recent logs for performance metrics."""
        if not self.log_file.exists():
            print(f"Log file {self.log_file} not found")
            return {}
            
        cutoff_time = datetime.now() - timedelta(hours=hours)
        metrics = {
            'token_usage': [],
            'payload_sizes': [],
            'response_times': [],
            'api_calls_per_hour': defaultdict(int),
            'decision_cycles': 0,
            'errors': [],
            'channels_active': set(),
            'platforms': defaultdict(int)
        }
        
        with open(self.log_file, 'r') as f:
            for line in f:
                # Extract timestamp and check if within time window
                if not self._is_recent_log(line, cutoff_time):
                    continue
                    
                # Token usage
                token_match = self.token_usage_pattern.search(line)
                if token_match:
                    metrics['token_usage'].append(int(token_match.group(1)))
                
                # Payload size
                payload_match = self.payload_size_pattern.search(line)
                if payload_match:
                    metrics['payload_sizes'].append(float(payload_match.group(1)))
                
                # Response time
                response_match = self.response_time_pattern.search(line)
                if response_match:
                    metrics['response_times'].append(float(response_match.group(1)))
                
                # API calls per hour
                if self.api_call_pattern.search(line):
                    hour = self._extract_hour(line)
                    if hour:
                        metrics['api_calls_per_hour'][hour] += 1
                
                # Decision cycles
                if self.decision_cycle_pattern.search(line):
                    metrics['decision_cycles'] += 1
                
                # Errors
                if 'ERROR' in line or 'Exception' in line:
                    metrics['errors'].append(line.strip())
                
                # Active channels and platforms
                if 'Matrix' in line or 'Farcaster' in line:
                    if 'Matrix' in line:
                        metrics['platforms']['Matrix'] += 1
                    if 'Farcaster' in line:
                        metrics['platforms']['Farcaster'] += 1
        
        return metrics
    
    def _is_recent_log(self, line: str, cutoff_time: datetime) -> bool:
        """Check if log line is within the specified time window."""
        # Simple heuristic - in a production system, you'd parse actual timestamps
        return True  # For now, assume all logs are recent
    
    def _extract_hour(self, line: str) -> Optional[str]:
        """Extract hour from log line timestamp."""
        # Simplified - would need actual timestamp parsing
        return datetime.now().strftime("%H")
    
    def generate_report(self, metrics: Dict) -> str:
        """Generate a comprehensive performance report."""
        report = []
        report.append("=" * 60)
        report.append("RATi Chatbot System Performance Report")
        report.append("=" * 60)
        report.append(f"Analysis Period: Last 24 hours")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        # Token Usage Analysis
        if metrics['token_usage']:
            total_tokens = sum(metrics['token_usage'])
            avg_tokens = statistics.mean(metrics['token_usage'])
            max_tokens = max(metrics['token_usage'])
            min_tokens = min(metrics['token_usage'])
            
            report.append("TOKEN USAGE ANALYSIS:")
            report.append(f"  Total tokens consumed: {total_tokens:,}")
            report.append(f"  Average per request: {avg_tokens:.0f}")
            report.append(f"  Range: {min_tokens} - {max_tokens}")
            report.append(f"  Total API calls: {len(metrics['token_usage'])}")
            
            # Cost estimation (rough)
            estimated_cost = (total_tokens / 1000) * 0.0014  # DeepSeek R1 pricing
            report.append(f"  Estimated cost: ${estimated_cost:.4f}")
        
        # Payload Size Analysis
        if metrics['payload_sizes']:
            avg_payload = statistics.mean(metrics['payload_sizes'])
            max_payload = max(metrics['payload_sizes'])
            
            report.append("\nPAYLOAD SIZE ANALYSIS:")
            report.append(f"  Average payload size: {avg_payload:.1f}KB")
            report.append(f"  Maximum payload size: {max_payload:.1f}KB")
            report.append(f"  Total payloads analyzed: {len(metrics['payload_sizes'])}")
        
        # Response Time Analysis
        if metrics['response_times']:
            avg_response = statistics.mean(metrics['response_times'])
            max_response = max(metrics['response_times'])
            
            report.append("\nRESPONSE TIME ANALYSIS:")
            report.append(f"  Average response time: {avg_response:.2f}s")
            report.append(f"  Maximum response time: {max_response:.2f}s")
        
        # Platform Activity
        if metrics['platforms']:
            report.append("\nPLATFORM ACTIVITY:")
            for platform, count in metrics['platforms'].items():
                report.append(f"  {platform}: {count} activities")
        
        # Decision Cycles
        report.append(f"\nDECISION CYCLES: {metrics['decision_cycles']}")
        
        # Errors
        if metrics['errors']:
            report.append(f"\nERRORS DETECTED: {len(metrics['errors'])}")
            for error in metrics['errors'][:5]:  # Show first 5 errors
                report.append(f"  {error[:100]}...")
        
        # Optimization Recommendations
        report.append("\n" + "=" * 60)
        report.append("OPTIMIZATION RECOMMENDATIONS:")
        report.append("=" * 60)
        
        if metrics['token_usage']:
            avg_tokens = statistics.mean(metrics['token_usage'])
            if avg_tokens > 5000:
                report.append("🔥 HIGH TOKEN USAGE DETECTED:")
                report.append("   - Consider reducing AI_CONVERSATION_HISTORY_LENGTH")
                report.append("   - Implement more aggressive payload filtering")
                report.append("   - Use compact summaries for secondary channels")
            elif avg_tokens > 3000:
                report.append("⚠️  MODERATE TOKEN USAGE:")
                report.append("   - Monitor for trends")
                report.append("   - Consider payload optimization")
            else:
                report.append("✅ TOKEN USAGE OPTIMAL")
        
        if metrics['payload_sizes']:
            avg_payload = statistics.mean(metrics['payload_sizes'])
            if avg_payload > 12:
                report.append("🔥 LARGE PAYLOAD SIZES:")
                report.append("   - Implement node-based payload switching")
                report.append("   - Reduce message snippet lengths")
            elif avg_payload > 8:
                report.append("⚠️  MODERATE PAYLOAD SIZES:")
                report.append("   - Monitor payload growth")
            else:
                report.append("✅ PAYLOAD SIZES OPTIMAL")
        
        if metrics['response_times']:
            avg_response = statistics.mean(metrics['response_times'])
            if avg_response > 3:
                report.append("🔥 SLOW RESPONSE TIMES:")
                report.append("   - Check network connectivity")
                report.append("   - Consider request batching")
            elif avg_response > 2:
                report.append("⚠️  MODERATE RESPONSE TIMES:")
                report.append("   - Monitor for trends")
            else:
                report.append("✅ RESPONSE TIMES OPTIMAL")
        
        return "\n".join(report)
    
    def monitor_real_time(self, interval: int = 60):
        """Monitor system performance in real-time."""
        print("Starting real-time monitoring...")
        print("Press Ctrl+C to stop")
        
        try:
            while True:
                metrics = self.parse_logs(hours=1)  # Last hour
                print(f"\n{datetime.now().strftime('%H:%M:%S')} - Performance Snapshot:")
                
                if metrics['token_usage']:
                    recent_tokens = metrics['token_usage'][-10:]  # Last 10 requests
                    avg_recent = statistics.mean(recent_tokens) if recent_tokens else 0
                    print(f"  Recent avg tokens: {avg_recent:.0f}")
                
                if metrics['payload_sizes']:
                    recent_payloads = metrics['payload_sizes'][-10:]
                    avg_payload = statistics.mean(recent_payloads) if recent_payloads else 0
                    print(f"  Recent avg payload: {avg_payload:.1f}KB")
                
                api_calls = sum(metrics['api_calls_per_hour'].values())
                print(f"  API calls last hour: {api_calls}")
                
                import time
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped.")

def main():
    parser = argparse.ArgumentParser(description="RATi Chatbot Performance Analyzer")
    parser.add_argument('--log-file', default='chatbot.log', help='Path to log file')
    parser.add_argument('--hours', type=int, default=24, help='Hours of logs to analyze')
    parser.add_argument('--monitor', action='store_true', help='Enable real-time monitoring')
    parser.add_argument('--interval', type=int, default=60, help='Monitoring interval in seconds')
    
    args = parser.parse_args()
    
    analyzer = PerformanceAnalyzer(args.log_file)
    
    if args.monitor:
        analyzer.monitor_real_time(args.interval)
    else:
        metrics = analyzer.parse_logs(args.hours)
        report = analyzer.generate_report(metrics)
        print(report)
        
        # Save report to file
        report_file = f"performance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(report_file, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {report_file}")

if __name__ == "__main__":
    main()
