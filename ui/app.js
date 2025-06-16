// Chatbot Management Dashboard JavaScript

let performanceChart;
let logWebSocket;

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupWebSocket();
    loadDashboardData();
    
    // Refresh data every 30 seconds
    setInterval(loadDashboardData, 30000);
});

function initializeApp() {
    console.log('Initializing Chatbot Management Dashboard');
    initializePerformanceChart();
}

function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/logs`;
    
    logWebSocket = new WebSocket(wsUrl);
    
    logWebSocket.onopen = function(event) {
        console.log('WebSocket connected');
        updateConnectionStatus(true);
    };
    
    logWebSocket.onmessage = function(event) {
        const logData = JSON.parse(event.data);
        addLogEntry(logData);
    };
    
    logWebSocket.onclose = function(event) {
        console.log('WebSocket disconnected');
        updateConnectionStatus(false);
        
        // Attempt to reconnect after 5 seconds
        setTimeout(setupWebSocket, 5000);
    };
    
    logWebSocket.onerror = function(error) {
        console.error('WebSocket error:', error);
        updateConnectionStatus(false);
    };
}

function updateConnectionStatus(connected) {
    const indicator = document.getElementById('status-indicator');
    const statusDot = indicator.querySelector('div');
    const statusText = indicator.querySelector('span');
    
    if (connected) {
        statusDot.className = 'w-3 h-3 bg-green-500 rounded-full mr-2';
        statusText.textContent = 'Connected';
    } else {
        statusDot.className = 'w-3 h-3 bg-red-500 rounded-full mr-2';
        statusText.textContent = 'Disconnected';
    }
}

async function loadDashboardData() {
    try {
        // Load system health
        const healthResponse = await fetch('/api/monitoring/health');
        if (healthResponse.ok) {
            const healthData = await healthResponse.json();
            updateSystemStatus(healthData);
        }
        
        // Load performance metrics
        const metricsResponse = await fetch('/api/monitoring/metrics');
        if (metricsResponse.ok) {
            const metricsData = await metricsResponse.json();
            updatePerformanceMetrics(metricsData);
        }
        
        // Load configuration
        const configResponse = await fetch('/api/monitoring/configuration');
        if (configResponse.ok) {
            const configData = await configResponse.json();
            updateConfiguration(configData);
        }
        
        // Load error statistics
        const errorsResponse = await fetch('/api/monitoring/errors/stats');
        if (errorsResponse.ok) {
            const errorsData = await errorsResponse.json();
            updateErrorStats(errorsData);
        }
        
    } catch (error) {
        console.error('Error loading dashboard data:', error);
        updateConnectionStatus(false);
    }
}

function updateSystemStatus(healthData) {
    // Update main status
    const systemStatus = document.getElementById('system-status');
    const isHealthy = healthData.overall_health === 'healthy';
    systemStatus.textContent = isHealthy ? 'Healthy' : 'Issues';
    systemStatus.className = `text-2xl font-bold ${isHealthy ? 'text-green-600' : 'text-red-600'}`;
    
    // Update uptime
    const uptime = document.getElementById('uptime');
    if (healthData.uptime_seconds) {
        const hours = Math.floor(healthData.uptime_seconds / 3600);
        const minutes = Math.floor((healthData.uptime_seconds % 3600) / 60);
        uptime.textContent = `${hours}h ${minutes}m`;
    }
    
    // Update active channels
    const activeChannels = document.getElementById('active-channels');
    if (healthData.components && healthData.components.world_state) {
        activeChannels.textContent = healthData.components.world_state.active_channels || '0';
    }
    
    // Update health details
    const healthDetails = document.getElementById('health-details');
    if (healthData.components) {
        healthDetails.innerHTML = '';
        Object.entries(healthData.components).forEach(([component, status]) => {
            const isHealthy = status.status === 'healthy';
            const div = document.createElement('div');
            div.className = 'flex justify-between items-center';
            div.innerHTML = `
                <span class="text-gray-600">${component.replace('_', ' ').toUpperCase()}</span>
                <span class="${isHealthy ? 'text-green-600' : 'text-red-600'} font-medium">
                    ${isHealthy ? '✓' : '✗'} ${status.status}
                </span>
            `;
            healthDetails.appendChild(div);
        });
    }
}

function updatePerformanceMetrics(metricsData) {
    if (metricsData.token_usage) {
        const tokenUsage = document.getElementById('token-usage');
        tokenUsage.textContent = metricsData.token_usage.total_today || '--';
    }
    
    // Update performance chart
    if (performanceChart && metricsData.response_times) {
        const labels = metricsData.response_times.map(item => new Date(item.timestamp).toLocaleTimeString());
        const data = metricsData.response_times.map(item => item.avg_response_time);
        
        performanceChart.data.labels = labels;
        performanceChart.data.datasets[0].data = data;
        performanceChart.update();
    }
}

function updateErrorStats(errorsData) {
    const errorCount = document.getElementById('error-count');
    const errorRate = document.getElementById('error-rate');
    
    if (errorsData) {
        errorCount.textContent = errorsData.total_errors_24h || '0';
        errorRate.textContent = errorsData.error_rate ? `${errorsData.error_rate.toFixed(2)}%` : '0%';
    }
}

function updateConfiguration(configData) {
    if (configData.ai) {
        const aiModel = document.getElementById('ai-model');
        const maxTokens = document.getElementById('max-tokens');
        
        if (aiModel) aiModel.value = configData.ai.model || '';
        if (maxTokens) maxTokens.value = configData.ai.max_tokens || '';
    }
    
    if (configData.system) {
        const environment = document.getElementById('environment');
        const version = document.getElementById('version');
        
        if (environment) environment.value = configData.system.environment || '';
        if (version) version.value = configData.system.version || '';
    }
}

function initializePerformanceChart() {
    const ctx = document.getElementById('performance-chart');
    if (!ctx) return;
    
    performanceChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Response Time (ms)',
                data: [],
                borderColor: 'rgb(59, 130, 246)',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    title: {
                        display: true,
                        text: 'Response Time (ms)'
                    }
                },
                x: {
                    title: {
                        display: true,
                        text: 'Time'
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                },
                title: {
                    display: true,
                    text: 'API Response Times'
                }
            }
        }
    });
}

function showTab(tabName) {
    // Hide all tab contents
    const tabContents = document.querySelectorAll('.tab-content');
    tabContents.forEach(content => content.classList.add('hidden'));
    
    // Remove active class from all tab buttons
    const tabButtons = document.querySelectorAll('.tab-button');
    tabButtons.forEach(button => {
        button.classList.remove('active', 'border-blue-600', 'text-blue-600');
        button.classList.add('border-transparent');
    });
    
    // Show selected tab content
    const selectedTab = document.getElementById(`${tabName}-tab`);
    if (selectedTab) {
        selectedTab.classList.remove('hidden');
    }
    
    // Add active class to selected tab button
    const selectedButton = event.target;
    selectedButton.classList.add('active', 'border-blue-600', 'text-blue-600');
    selectedButton.classList.remove('border-transparent');
}

function addLogEntry(logData) {
    const logsContainer = document.getElementById('logs-container');
    const logLevel = document.getElementById('log-level').value;
    
    // Filter by log level if needed
    if (logLevel !== 'all' && logData.level.toLowerCase() !== logLevel.toLowerCase()) {
        return;
    }
    
    const timestamp = new Date(logData.timestamp).toLocaleTimeString();
    const logEntry = document.createElement('div');
    logEntry.className = 'mb-1';
    
    const levelColor = {
        'ERROR': 'text-red-400',
        'WARNING': 'text-yellow-400',
        'INFO': 'text-green-400',
        'DEBUG': 'text-blue-400'
    }[logData.level.toUpperCase()] || 'text-green-400';
    
    logEntry.innerHTML = `
        <span class="text-gray-500">[${timestamp}]</span>
        <span class="${levelColor}">[${logData.level.toUpperCase()}]</span>
        <span class="text-white">${logData.message}</span>
    `;
    
    logsContainer.appendChild(logEntry);
    
    // Keep only last 100 log entries
    while (logsContainer.children.length > 100) {
        logsContainer.removeChild(logsContainer.firstChild);
    }
    
    // Auto-scroll to bottom
    logsContainer.scrollTop = logsContainer.scrollHeight;
}

function clearLogs() {
    const logsContainer = document.getElementById('logs-container');
    logsContainer.innerHTML = '<div>Logs cleared...</div>';
}

function refreshData() {
    loadDashboardData();
    console.log('Dashboard data refreshed');
    
    // Show visual feedback
    const refreshButton = event.target;
    const originalText = refreshButton.innerHTML;
    refreshButton.innerHTML = '<i class="fas fa-spinner fa-spin mr-1"></i> Refreshing...';
    refreshButton.disabled = true;
    
    setTimeout(() => {
        refreshButton.innerHTML = originalText;
        refreshButton.disabled = false;
    }, 1000);
}

// CSS styles for active tab
const style = document.createElement('style');
style.textContent = `
    .tab-button.active {
        color: rgb(37, 99, 235) !important;
        border-bottom-color: rgb(37, 99, 235) !important;
    }
`;
document.head.appendChild(style);
