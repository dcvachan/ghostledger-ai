/**
 * GhostLedger AI - Dashboard Analytics & Chart.js Config
 */

document.addEventListener('DOMContentLoaded', () => {
    initCharts();
});

function initCharts() {
    const matchChartCanvas = document.getElementById('matchDoughnutChart');
    const categoryChartCanvas = document.getElementById('discrepancyBarChart');

    if (!matchChartCanvas && !categoryChartCanvas) return;

    // Fetch dynamic metrics from API
    fetch('/api/metrics')
        .then(res => res.json())
        .then(data => {
            if (matchChartCanvas) {
                renderMatchChart(matchChartCanvas, data);
            }
            if (categoryChartCanvas) {
                renderCategoryChart(categoryChartCanvas, data);
            }
        })
        .catch(err => console.error("Failed to load dashboard metrics for charts:", err));
}

function renderMatchChart(canvas, data) {
    const ctx = canvas.getContext('2d');
    const matched = data.matched_records || 0;
    const discrepancies = data.open_exceptions_count || 0;
    const resolved = data.resolved_exceptions_count || 0;
    const remainingUnmatched = Math.max(0, (data.unmatched_records || 0) - discrepancies);

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Matched Records', 'Active Exceptions', 'Resolved Exceptions', 'Unmatched/Pending'],
            datasets: [{
                data: [matched, discrepancies, resolved, remainingUnmatched],
                backgroundColor: [
                    '#00875a', // Green
                    '#de350b', // Red
                    '#2962ff', // Electric Blue
                    '#dfe1e6'  // Light Grey
                ],
                borderWidth: 2,
                borderColor: '#ffffff',
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '72%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        boxWidth: 12,
                        padding: 16,
                        font: { family: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif', size: 12 }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const val = context.raw || 0;
                            const total = data.total_records || 1;
                            const pct = ((val / total) * 100).toFixed(1);
                            return ` ${context.label}: ${val} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

function renderCategoryChart(canvas, data) {
    const ctx = canvas.getContext('2d');
    const breakdown = data.discrepancy_breakdown || {};
    
    const labels = Object.keys(breakdown).map(k => k.replace(/_/g, ' '));
    const counts = Object.values(breakdown);

    if (labels.length === 0) {
        labels.push('No Discrepancies');
        counts.push(0);
    }

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Exceptions Flagged',
                data: counts,
                backgroundColor: '#2962ff',
                borderRadius: 4,
                maxBarThickness: 32
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1,
                        font: { size: 11 }
                    },
                    grid: {
                        color: '#ebecf0'
                    }
                },
                x: {
                    ticks: {
                        font: { size: 10 }
                    },
                    grid: {
                        display: false
                    }
                }
            },
            plugins: {
                legend: {
                    display: false
                }
            }
        }
    });
}
