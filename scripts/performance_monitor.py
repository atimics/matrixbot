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

    def analyze_farcaster_engagement_opportunities(self, hours: int = 24) -> Dict:
        """Analyze Farcaster functionality and engagement opportunities from logs."""
        if not self.log_file.exists():
            return {"error": "Log file not found"}
            
        cutoff_time = datetime.now() - timedelta(hours=hours)
        analysis = {
            'visibility_metrics': {
                'data_collection': {
                    'trending_casts': 0,
                    'home_feed': 0,
                    'notifications': 0,
                    'token_holders': 0,
                    'world_state_collections': 0
                },
                'channel_discovery': set(),
                'user_profiles_tracked': set(),
                'feed_types_active': set()
            },
            'engagement_opportunities': {
                'reply_opportunities': [],
                'trending_topics': [],
                'high_engagement_casts': [],
                'token_holder_interactions': [],
                'unaddressed_mentions': []
            },
            'intelligence_depth': {
                'ecosystem_token_holders': 0,
                'user_context_profiles': 0,
                'conversation_threads': 0,
                'sentiment_analysis': 0
            },
            'technical_health': {
                'api_calls_successful': 0,
                'api_errors': 0,
                'rate_limit_warnings': 0,
                'world_state_updates': 0,
                'processing_cycles': 0
            },
            'recommendation_priorities': []
        }
        
        # Track conversation contexts and engagement patterns
        conversation_contexts = {}
        cast_engagement_metrics = {}
        
        with open(self.log_file, 'r') as f:
            for line in f:
                if not self._is_recent_log(line, cutoff_time):
                    continue
                    
                # World State Collection Analysis
                if 'World state collection: stored' in line:
                    analysis['visibility_metrics']['data_collection']['world_state_collections'] += 1
                    if 'trending' in line:
                        analysis['visibility_metrics']['data_collection']['trending_casts'] += self._extract_number(line, 'messages')
                    if 'home' in line:
                        analysis['visibility_metrics']['data_collection']['home_feed'] += self._extract_number(line, 'messages')
                    if 'notifications' in line:
                        analysis['visibility_metrics']['data_collection']['notifications'] += self._extract_number(line, 'messages')
                
                # Token Holder Intelligence
                if 'Updated' in line and 'recent casts for holder FID' in line:
                    fid = self._extract_fid(line)
                    if fid:
                        analysis['visibility_metrics']['user_profiles_tracked'].add(fid)
                        analysis['visibility_metrics']['data_collection']['token_holders'] += self._extract_number(line, 'added')
                
                # Channel Discovery
                if 'Added matrix channel' in line or 'Added farcaster channel' in line:
                    channel_name = self._extract_channel_name(line)
                    if channel_name:
                        analysis['visibility_metrics']['channel_discovery'].add(channel_name)
                        
                        # Determine feed type
                        if 'farcaster:holders' in line:
                            analysis['visibility_metrics']['feed_types_active'].add('token_holders')
                        elif 'farcaster:home' in line:
                            analysis['visibility_metrics']['feed_types_active'].add('home_feed')
                        elif 'farcaster:trending' in line:
                            analysis['visibility_metrics']['feed_types_active'].add('trending')
                
                # Engagement Opportunity Detection
                if 'New message in' in line and 'farcaster' in line.lower():
                    cast_data = self._parse_farcaster_message(line)
                    if cast_data:
                        # Check for high engagement potential
                        if any(keyword in cast_data.get('content', '').lower() 
                               for keyword in ['question', '?', 'thoughts', 'opinion', 'what do you think']):
                            analysis['engagement_opportunities']['reply_opportunities'].append({
                                'channel': cast_data.get('channel'),
                                'user': cast_data.get('user'),
                                'content_preview': cast_data.get('content', '')[:100],
                                'timestamp': self._extract_timestamp(line),
                                'engagement_type': 'question_response'
                            })
                        
                        # Track trending topics
                        if 'trending' in cast_data.get('channel', ''):
                            analysis['engagement_opportunities']['trending_topics'].append({
                                'content': cast_data.get('content', '')[:100],
                                'user': cast_data.get('user'),
                                'timestamp': self._extract_timestamp(line)
                            })
                
                # Bot Response Analysis
                if 'Sent reply to' in line or 'Created Farcaster cast' in line:
                    analysis['technical_health']['processing_cycles'] += 1
                
                # API Health Monitoring
                if 'HTTP Request:' in line and 'neynar.com' in line:
                    if '200 OK' in line:
                        analysis['technical_health']['api_calls_successful'] += 1
                    else:
                        analysis['technical_health']['api_errors'] += 1
                
                # Rate Limit Monitoring
                if 'rate limit' in line.lower():
                    analysis['technical_health']['rate_limit_warnings'] += 1
                
                # Intelligence Depth Tracking
                if 'ecosystem_token_info' in line or 'monitored_token_holders' in line:
                    analysis['intelligence_depth']['ecosystem_token_holders'] += 1
                
                if 'FarcasterUserDetails' in line or 'Updated profile for Farcaster user' in line:
                    analysis['intelligence_depth']['user_context_profiles'] += 1
                
                if 'thread' in line.lower() and 'expand' in line.lower():
                    analysis['intelligence_depth']['conversation_threads'] += 1
        
        # Generate Recommendations
        analysis['recommendation_priorities'] = self._generate_engagement_recommendations(analysis)
        
        # Convert sets to lists for JSON serialization
        for key in analysis['visibility_metrics']:
            if isinstance(analysis['visibility_metrics'][key], set):
                analysis['visibility_metrics'][key] = list(analysis['visibility_metrics'][key])
        
        return analysis
    
    def _extract_number(self, line: str, context: str) -> int:
        """Extract number from log line in given context."""
        try:
            if context in line:
                parts = line.split(context)
                if len(parts) > 1:
                    # Look for number before the context word
                    before = parts[0].split()[-1] if parts[0].split() else "0"
                    return int(before) if before.isdigit() else 0
        except:
            pass
        return 0
    
    def _extract_fid(self, line: str) -> Optional[str]:
        """Extract Farcaster ID from log line."""
        import re
        fid_match = re.search(r'FID (\d+)', line)
        return fid_match.group(1) if fid_match else None
    
    def _extract_channel_name(self, line: str) -> Optional[str]:
        """Extract channel name from log line."""
        import re
        # Look for channel names in quotes or after 'channel'
        channel_match = re.search(r"'([^']+)'", line)
        if channel_match:
            return channel_match.group(1)
        return None
    
    def _parse_farcaster_message(self, line: str) -> Optional[Dict]:
        """Parse Farcaster message details from log line."""
        try:
            if 'New message in' in line:
                parts = line.split(': ', 2)
                if len(parts) >= 3:
                    channel_part = parts[1]
                    message_part = parts[2]
                    
                    # Extract channel
                    channel = channel_part.split(' in ')[-1] if ' in ' in channel_part else channel_part
                    
                    # Extract user and content
                    if ': ' in message_part:
                        user, content = message_part.split(': ', 1)
                        return {
                            'channel': channel,
                            'user': user,
                            'content': content
                        }
        except:
            pass
        return None
    
    def _extract_timestamp(self, line: str) -> Optional[str]:
        """Extract timestamp from log line."""
        import re
        timestamp_match = re.match(r'^([0-9-]+ [0-9:,]+)', line)
        return timestamp_match.group(1) if timestamp_match else None
    
    def _generate_engagement_recommendations(self, analysis: Dict) -> List[Dict]:
        """Generate prioritized engagement recommendations based on analysis."""
        recommendations = []
        
        # High Priority: Unaddressed Mentions/Notifications
        if analysis['visibility_metrics']['data_collection']['notifications'] > 0:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Direct Engagement',
                'recommendation': 'Address pending notifications and mentions',
                'reasoning': f"Found {analysis['visibility_metrics']['data_collection']['notifications']} notifications that may require responses",
                'action': 'Review farcaster:notifications channel and respond to relevant mentions'
            })
        
        # High Priority: Token Holder Engagement
        if analysis['visibility_metrics']['data_collection']['token_holders'] > 0:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Community Engagement',
                'recommendation': 'Engage with ecosystem token holders',
                'reasoning': f"Monitoring {len(analysis['visibility_metrics']['user_profiles_tracked'])} token holders with {analysis['visibility_metrics']['data_collection']['token_holders']} recent casts",
                'action': 'Reply to or engage with meaningful token holder content to build community relationships'
            })
        
        # Medium Priority: Trending Topic Participation
        if analysis['visibility_metrics']['data_collection']['trending_casts'] > 0:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'Discovery & Growth',
                'recommendation': 'Participate in trending conversations',
                'reasoning': f"Collected {analysis['visibility_metrics']['data_collection']['trending_casts']} trending casts",
                'action': 'Add valuable insights to trending discussions to increase visibility'
            })
        
        # Medium Priority: Home Feed Engagement
        if analysis['visibility_metrics']['data_collection']['home_feed'] > 0:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'Social Presence',
                'recommendation': 'Engage with home feed content',
                'reasoning': f"Home feed shows {analysis['visibility_metrics']['data_collection']['home_feed']} messages from followed accounts",
                'action': 'Like, reply to, or recast content from accounts you follow to maintain social presence'
            })
        
        # Technical Health Recommendations
        if analysis['technical_health']['api_errors'] > analysis['technical_health']['api_calls_successful'] * 0.1:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Technical Health',
                'recommendation': 'Address API reliability issues',
                'reasoning': f"High error rate: {analysis['technical_health']['api_errors']} errors vs {analysis['technical_health']['api_calls_successful']} successful calls",
                'action': 'Investigate API connectivity and implement better error handling'
            })
        
        # Rate Limit Management
        if analysis['technical_health']['rate_limit_warnings'] > 0:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'Technical Optimization',
                'recommendation': 'Optimize API usage to avoid rate limits',
                'reasoning': f"Detected {analysis['technical_health']['rate_limit_warnings']} rate limit warnings",
                'action': 'Implement smarter request batching and timing to stay within rate limits'
            })
        
        # Intelligence Depth Enhancement
        if analysis['intelligence_depth']['conversation_threads'] < 5:
            recommendations.append({
                'priority': 'LOW',
                'category': 'Context Enhancement',
                'recommendation': 'Expand conversation thread analysis',
                'reasoning': 'Limited thread expansion detected, missing conversational context',
                'action': 'Use expand_node more frequently on interesting conversations to understand full context'
            })
        
        return sorted(recommendations, key=lambda x: {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}[x['priority']], reverse=True)

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
