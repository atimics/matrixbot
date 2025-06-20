"""
Dynamic payload optimization system for RATi Chatbot.
Automatically adjusts payload parameters based on recent performance metrics.
"""

import json
import logging
import os
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OptimizationMetrics:
    """Metrics for payload optimization decisions."""
    avg_token_usage: float
    max_token_usage: int
    avg_payload_size: float
    max_payload_size: float
    avg_response_time: float
    error_rate: float
    api_calls_per_hour: int
    timestamp: datetime

class DynamicPayloadOptimizer:
    """
    Dynamically optimizes payload parameters based on performance metrics.
    """
    
    def __init__(self):
        # Remove config_file parameter - use environment variables instead
        self.metrics_file = Path("data/optimization_metrics.json")
        self.optimization_history = []
        self.load_metrics_history()
        
        # Optimization thresholds
        self.HIGH_TOKEN_THRESHOLD = 5500
        self.MODERATE_TOKEN_THRESHOLD = 4000
        self.HIGH_PAYLOAD_THRESHOLD = 12.0  # KB
        self.MODERATE_PAYLOAD_THRESHOLD = 8.0  # KB
        self.HIGH_RESPONSE_THRESHOLD = 3.0  # seconds
        
    def load_metrics_history(self):
        """Load historical optimization metrics."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file, 'r') as f:
                    data = json.load(f)
                    self.optimization_history = [
                        OptimizationMetrics(
                            avg_token_usage=m['avg_token_usage'],
                            max_token_usage=m['max_token_usage'],
                            avg_payload_size=m['avg_payload_size'],
                            max_payload_size=m['max_payload_size'],
                            avg_response_time=m['avg_response_time'],
                            error_rate=m['error_rate'],
                            api_calls_per_hour=m['api_calls_per_hour'],
                            timestamp=datetime.fromisoformat(m['timestamp'])
                        )
                        for m in data
                    ]
            except Exception as e:
                logger.error(f"Failed to load metrics history: {e}")
                self.optimization_history = []
    
    def save_metrics_history(self):
        """Save optimization metrics history."""
        try:
            data = [
                {
                    'avg_token_usage': m.avg_token_usage,
                    'max_token_usage': m.max_token_usage,
                    'avg_payload_size': m.avg_payload_size,
                    'max_payload_size': m.max_payload_size,
                    'avg_response_time': m.avg_response_time,
                    'error_rate': m.error_rate,
                    'api_calls_per_hour': m.api_calls_per_hour,
                    'timestamp': m.timestamp.isoformat()
                }
                for m in self.optimization_history[-100:]  # Keep last 100 entries
            ]
            
            # Ensure directory exists
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics history: {e}")
    
    def analyze_current_performance(self) -> OptimizationMetrics:
        """Analyze current performance from logs."""
        # This would integrate with the performance monitor
        # For now, return placeholder metrics
        return OptimizationMetrics(
            avg_token_usage=4500,
            max_token_usage=6500,
            avg_payload_size=9.5,
            max_payload_size=11.2,
            avg_response_time=1.8,
            error_rate=0.02,
            api_calls_per_hour=25,
            timestamp=datetime.now()
        )
    
    def calculate_optimization_parameters(self, metrics: OptimizationMetrics) -> Dict[str, int]:
        """Calculate optimal parameters based on current metrics."""
        params = {}
        
        # Base parameters (conservative defaults)
        base_params = {
            'AI_CONVERSATION_HISTORY_LENGTH': 8,
            'AI_ACTION_HISTORY_LENGTH': 5,
            'AI_THREAD_HISTORY_LENGTH': 5,
            'AI_OTHER_CHANNELS_SUMMARY_COUNT': 3,
            'AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH': 75,
        }
        
        # Adjust based on token usage
        if metrics.avg_token_usage > self.HIGH_TOKEN_THRESHOLD:
            # Aggressive optimization
            params.update({
                'AI_CONVERSATION_HISTORY_LENGTH': 4,
                'AI_ACTION_HISTORY_LENGTH': 2,
                'AI_THREAD_HISTORY_LENGTH': 2,
                'AI_OTHER_CHANNELS_SUMMARY_COUNT': 1,
                'AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH': 40,
            })
            logger.info("Applying aggressive token optimization")
            
        elif metrics.avg_token_usage > self.MODERATE_TOKEN_THRESHOLD:
            # Moderate optimization
            params.update({
                'AI_CONVERSATION_HISTORY_LENGTH': 6,
                'AI_ACTION_HISTORY_LENGTH': 3,
                'AI_THREAD_HISTORY_LENGTH': 3,
                'AI_OTHER_CHANNELS_SUMMARY_COUNT': 2,
                'AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH': 50,
            })
            logger.info("Applying moderate token optimization")
            
        else:
            # Standard parameters
            params.update(base_params)
            logger.info("Using standard parameters")
        
        # Adjust based on payload size
        if metrics.avg_payload_size > self.HIGH_PAYLOAD_THRESHOLD:
            params['AI_OTHER_CHANNELS_SUMMARY_COUNT'] = max(1, params.get('AI_OTHER_CHANNELS_SUMMARY_COUNT', 2) - 1)
            params['AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH'] = max(30, params.get('AI_OTHER_CHANNELS_MESSAGE_SNIPPET_LENGTH', 50) - 10)
            logger.info("Applying payload size optimization")
        
        # Adjust based on response time
        if metrics.avg_response_time > self.HIGH_RESPONSE_THRESHOLD:
            # Reduce payload complexity
            params['AI_CONVERSATION_HISTORY_LENGTH'] = max(3, params.get('AI_CONVERSATION_HISTORY_LENGTH', 6) - 1)
            params['AI_ACTION_HISTORY_LENGTH'] = max(2, params.get('AI_ACTION_HISTORY_LENGTH', 3) - 1)
            logger.info("Applying response time optimization")
        
        return params
    
    def update_environment_variables(self, params: Dict[str, int]) -> bool:
        """Update environment variables with new parameters."""
        try:
            # Read current .env file
            env_file = Path('.env')
            if not env_file.exists():
                logger.error(".env file not found")
                return False
            
            with open(env_file, 'r') as f:
                lines = f.readlines()
            
            # Update parameters
            updated = False
            for i, line in enumerate(lines):
                for param, value in params.items():
                    if line.startswith(f"{param}="):
                        old_value = line.strip().split('=')[1]
                        if old_value != str(value):
                            lines[i] = f"{param}={value}\n"
                            logger.info(f"Updated {param}: {old_value} -> {value}")
                            updated = True
                        break
            
            # Write back to file if changes were made
            if updated:
                with open(env_file, 'w') as f:
                    f.writelines(lines)
                logger.info("Environment variables updated")
                return True
            else:
                logger.info("No optimization changes needed")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update environment variables: {e}")
            return False
    
    def should_optimize(self, metrics: OptimizationMetrics) -> bool:
        """Determine if optimization is needed based on metrics."""
        return (
            metrics.avg_token_usage > self.MODERATE_TOKEN_THRESHOLD or
            metrics.avg_payload_size > self.MODERATE_PAYLOAD_THRESHOLD or
            metrics.avg_response_time > self.HIGH_RESPONSE_THRESHOLD or
            metrics.error_rate > 0.05
        )
    
    def run_optimization_cycle(self) -> bool:
        """Run a complete optimization cycle."""
        logger.info("Starting optimization cycle")
        
        # Analyze current performance
        metrics = self.analyze_current_performance()
        
        # Store metrics
        self.optimization_history.append(metrics)
        self.save_metrics_history()
        
        # Check if optimization is needed
        if not self.should_optimize(metrics):
            logger.info("Performance is within acceptable thresholds, no optimization needed")
            return False
        
        # Calculate optimal parameters
        optimal_params = self.calculate_optimization_parameters(metrics)
        
        # Update environment variables
        updated = self.update_environment_variables(optimal_params)
        
        if updated:
            logger.info("Optimization cycle completed successfully")
            # Note: In a production system, you might want to restart the service
            # or reload configuration to apply changes
        
        return updated
    
    def generate_optimization_report(self) -> str:
        """Generate a report on optimization history and recommendations."""
        if not self.optimization_history:
            return "No optimization history available"
        
        recent_metrics = self.optimization_history[-10:]  # Last 10 entries
        
        report = ["Dynamic Payload Optimization Report", "=" * 40]
        report.append(f"Analysis period: {len(recent_metrics)} recent measurements")
        report.append("")
        
        # Current performance
        latest = recent_metrics[-1]
        report.append("CURRENT PERFORMANCE:")
        report.append(f"  Average token usage: {latest.avg_token_usage:.0f}")
        report.append(f"  Average payload size: {latest.avg_payload_size:.1f}KB")
        report.append(f"  Average response time: {latest.avg_response_time:.2f}s")
        report.append(f"  Error rate: {latest.error_rate:.1%}")
        report.append("")
        
        # Trends
        if len(recent_metrics) > 1:
            token_trend = recent_metrics[-1].avg_token_usage - recent_metrics[0].avg_token_usage
            payload_trend = recent_metrics[-1].avg_payload_size - recent_metrics[0].avg_payload_size
            
            report.append("TRENDS:")
            report.append(f"  Token usage trend: {token_trend:+.0f}")
            report.append(f"  Payload size trend: {payload_trend:+.1f}KB")
            report.append("")
        
        # Recommendations
        report.append("RECOMMENDATIONS:")
        if latest.avg_token_usage > self.HIGH_TOKEN_THRESHOLD:
            report.append("  🔥 High token usage - aggressive optimization recommended")
        elif latest.avg_token_usage > self.MODERATE_TOKEN_THRESHOLD:
            report.append("  ⚠️  Moderate token usage - consider optimization")
        else:
            report.append("  ✅ Token usage is optimal")
        
        if latest.avg_payload_size > self.HIGH_PAYLOAD_THRESHOLD:
            report.append("  🔥 Large payload sizes - reduce channel summaries")
        elif latest.avg_payload_size > self.MODERATE_PAYLOAD_THRESHOLD:
            report.append("  ⚠️  Moderate payload sizes - monitor closely")
        else:
            report.append("  ✅ Payload sizes are optimal")
        
        return "\n".join(report)

def main():
    """Run optimization system."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dynamic Payload Optimizer")
    parser.add_argument('--run', action='store_true', help='Run optimization cycle')
    parser.add_argument('--report', action='store_true', help='Generate optimization report')
    parser.add_argument('--continuous', action='store_true', help='Run continuous optimization')
    parser.add_argument('--interval', type=int, default=3600, help='Optimization interval (seconds)')
    
    args = parser.parse_args()
    
    optimizer = DynamicPayloadOptimizer()
    
    if args.report:
        print(optimizer.generate_optimization_report())
    elif args.run:
        optimizer.run_optimization_cycle()
    elif args.continuous:
        import time
        print("Starting continuous optimization...")
        try:
            while True:
                optimizer.run_optimization_cycle()
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("Optimization stopped")
    else:
        print("Use --run, --report, or --continuous")

if __name__ == "__main__":
    main()
