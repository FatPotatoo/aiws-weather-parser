// Global Variables
let map;
let rainfallLayer = null;
let hoverRect = null;
let distributionChart = null;
let currentRainfallData = null;
let animationInterval = null;
let isPlaying = false;

// Color mapping for rainfall (Canvas pixel colors: R, G, B, A)
const RAINFALL_COLORS = [
    { limit: 0.1,   color: { r: 255, g: 255, b: 255, a: 35 } },      // No Rain (Soft Semi-Transparent White)
    { limit: 2.5,   color: { r: 165, g: 243, b: 252, a: 180 } },    // Light Rain (Cyan 200)
    { limit: 7.5,   color: { r: 56,  g: 189, b: 248, a: 180 } },    // Moderate Rain (Sky 400)
    { limit: 19.0,  color: { r: 2,   g: 132, b: 199, a: 190 } },    // Rather Heavy (Sky 600)
    { limit: 35.5,  color: { r: 3,   g: 105, b: 161, a: 195 } },    // Heavy (Sky 700)
    { limit: 64.5,  color: { r: 29,  g: 78,  b: 216, a: 200 } },    // Very Heavy (Blue 700)
    { limit: 124.5, color: { r: 124, g: 58,  b: 237, a: 215 } },    // Ext. Heavy (Violet 600)
    { limit: Infinity, color: { r: 220, g: 38,  b: 38,  a: 235 } }     // Torrential (Red 600)
];

// Document Ready
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Lucide Icons
    lucide.createIcons();
    
    // Initialize Map
    initMap();
    
    // Initialize Event Listeners
    // Initialize Event Listeners (safe: initEventListeners checks element existence)
    initEventListeners();

    // Check for date in URL parameters — when this page is embedded we expect a date param.
    const urlParams = new URLSearchParams(window.location.search);
    const urlDate = urlParams.get('date');
    const datePicker = document.getElementById('date-picker');
    const hiddenDatePicker = document.getElementById('hidden-date-picker');

    if (urlDate) {
        const parsed = parseCustomDate(urlDate);
        const currentYear = new Date().getFullYear();
        if (parsed && parsed.y >= 2020 && parsed.y <= currentYear) {
            const formatted = `${parsed.y}-${String(parsed.m).padStart(2, '0')}-${String(parsed.d).padStart(2, '0')}`;
            if (datePicker) datePicker.value = formatted;
            if (hiddenDatePicker) hiddenDatePicker.value = formatted;
            fetchRainfallData(formatted);
            return;
        }
    }

    // If no URL date provided and no date picker present, fetch a sensible default (first day of 2025 or current date)
    if (datePicker) {
        fetchRainfallData(datePicker.value);
    } else if (urlDate) {
        fetchRainfallData(urlDate);
    } else {
        const currentYear = new Date().getFullYear();
        const defaultDate = currentYear <= 2025 ? '2025-01-01' : '2026-06-01';
        fetchRainfallData(defaultDate);
    }
});

// Initialize Leaflet Map
function initMap() {
    // Center of India
    map = L.map('map', {
        zoomControl: false,
        attributionControl: true
    }).setView([22.9734, 78.6569], 5);
    
    // Add Zoom Control to Top Right
    L.control.zoom({
        position: 'topright'
    }).addTo(map);
    
    // Add Dark Matter Tile Layer
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        subdomains: 'abcd',
        maxZoom: 20
    }).addTo(map);

    // Map Hover Events
    map.on('mousemove', handleMapHover);
    map.on('mouseout', handleMapMouseOut);
}

// Initialize Event Listeners
function initEventListeners() {
    const datePicker = document.getElementById('date-picker');
    const hiddenDatePicker = document.getElementById('hidden-date-picker');
    const calendarBtn = document.getElementById('calendar-trigger-btn');
    const prevBtn = document.getElementById('prev-day-btn');
    const nextBtn = document.getElementById('next-day-btn');
    const playBtn = document.getElementById('play-btn');
    const focusMaxBtn = document.getElementById('focus-max-btn');

    // Safely bind listeners only when elements exist (we removed the date UI for embedded use)
    if (datePicker) {
        datePicker.addEventListener('change', () => {
            if (isPlaying) stopTimelineAnimation();
            handleTypedDate();
        });

        datePicker.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') datePicker.blur();
        });
    }

    if (calendarBtn && hiddenDatePicker) {
        calendarBtn.addEventListener('click', () => {
            if (isPlaying) stopTimelineAnimation();
            try { hiddenDatePicker.showPicker(); } catch (err) { hiddenDatePicker.click(); }
        });

        hiddenDatePicker.addEventListener('change', (e) => {
            if (isPlaying) stopTimelineAnimation();
            const selectedDate = e.target.value;
            if (datePicker) datePicker.value = selectedDate;
            if (datePicker) datePicker.classList.remove('input-error');
            fetchRainfallData(selectedDate);
        });
    }

    if (prevBtn) prevBtn.addEventListener('click', () => { if (isPlaying) stopTimelineAnimation(); changeDate(-1); });
    if (nextBtn) nextBtn.addEventListener('click', () => { if (isPlaying) stopTimelineAnimation(); changeDate(1); });
    if (playBtn) playBtn.addEventListener('click', toggleTimelineAnimation);
    if (focusMaxBtn) focusMaxBtn.addEventListener('click', centerOnMaxRainfall);
}

// Parse custom date formats: YYYY-MM-DD, DD-MM-YYYY, YYYY/MM/DD, DD/MM/YYYY
function parseCustomDate(str) {
    str = str.trim();
    
    // YYYY-MM-DD or YYYY/MM/DD
    let match = str.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
    if (match) {
        return { y: parseInt(match[1]), m: parseInt(match[2]), d: parseInt(match[3]) };
    }
    
    // DD-MM-YYYY or DD/MM/YYYY
    match = str.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$/);
    if (match) {
        return { y: parseInt(match[3]), m: parseInt(match[2]), d: parseInt(match[1]) };
    }
    
    return null;
}

// Handle typed custom date
function handleTypedDate() {
    const datePicker = document.getElementById('date-picker');
    const hiddenDatePicker = document.getElementById('hidden-date-picker');
    const val = datePicker.value;
    
    const parsed = parseCustomDate(val);
    if (parsed) {
        // Validate year is between 2020 and current year
        const currentYear = new Date().getFullYear();
        if (parsed.y < 2020 || parsed.y > currentYear) {
            alert(`Only dates between 2020 and ${currentYear} are supported.`);
            datePicker.classList.add('input-error');
            return;
        }
        
        // Validate date is real
        const dateObj = new Date(parsed.y, parsed.m - 1, parsed.d);
        if (dateObj.getFullYear() === parsed.y && dateObj.getMonth() === parsed.m - 1 && dateObj.getDate() === parsed.d) {
            datePicker.classList.remove('input-error');
            
            // Format to YYYY-MM-DD
            const formatted = `${parsed.y}-${String(parsed.m).padStart(2, '0')}-${String(parsed.d).padStart(2, '0')}`;
            datePicker.value = formatted;
            hiddenDatePicker.value = formatted;
            
            fetchRainfallData(formatted);
            return;
        }
    }
    
    // Invalid date
    datePicker.classList.add('input-error');
    alert('Invalid date. Please use YYYY-MM-DD or DD-MM-YYYY format.');
}

// Change Date by offset (in days)
function changeDate(daysOffset) {
    const datePicker = document.getElementById('date-picker');
    const hiddenDatePicker = document.getElementById('hidden-date-picker');
    
    let currentDate = new Date(hiddenDatePicker.value);
    
    // Add offset
    currentDate.setDate(currentDate.getDate() + daysOffset);
    
    // Clamp between 2020-01-01 and today
    const minDate = new Date('2020-01-01');
    const maxDate = new Date();
    
    if (currentDate < minDate) {
        currentDate = minDate;
        if (isPlaying) stopTimelineAnimation();
    } else if (currentDate > maxDate) {
        currentDate = maxDate;
        if (isPlaying) stopTimelineAnimation();
    }
    
    // Format back to YYYY-MM-DD
    const yyyy = currentDate.getFullYear();
    const mm = String(currentDate.getMonth() + 1).padStart(2, '0');
    const dd = String(currentDate.getDate()).padStart(2, '0');
    const formattedDate = `${yyyy}-${mm}-${dd}`;
    
    datePicker.value = formattedDate;
    hiddenDatePicker.value = formattedDate;
    datePicker.classList.remove('input-error');
    
    fetchRainfallData(formattedDate);
}

// Fetch data from PHP backend
function fetchRainfallData(dateStr) {
    showLoading(true);
    
    fetch(`get_data.php?date=${dateStr}`)
        .then(response => response.text())
        .then(text => {
            showLoading(false);
            let data = null;
            try {
                data = JSON.parse(text);
            } catch (e) {
                console.error('Invalid JSON from server:', text);
                if (isPlaying) stopTimelineAnimation();
                const short = text.length > 500 ? text.slice(0, 500) + '\n...[truncated]' : text;
                alert('Server error while loading rainfall data. See console for details.\n\n' + short);
                return;
            }

            if (data.error) {
                alert(data.error + (data.details ? '\n\nDetails: ' + data.details : ''));
                if (isPlaying) stopTimelineAnimation();
                return;
            }

            currentRainfallData = data;
            updateUI(data);
        })
        .catch(err => {
            showLoading(false);
            console.error('Error fetching data:', err);
            if (isPlaying) stopTimelineAnimation();
            alert('Failed to load rainfall data. Make sure your local server is running.\nSee console for network error.');
        });
}

// Update the UI with fetched data
function updateUI(data) {
    // 1. Update Stats
    document.getElementById('stat-mean').innerHTML = `${data.stats.mean_rainfall.toFixed(1)} <span class="unit">mm</span>`;
    document.getElementById('stat-area').innerHTML = `${data.stats.rain_area_percentage.toFixed(1)} <span class="unit">%</span>`;
    document.getElementById('stat-max').innerHTML = `${data.stats.max_rainfall.toFixed(1)} <span class="unit">mm</span>`;
    
    const lat = data.stats.max_location.latitude;
    const lon = data.stats.max_location.longitude;
    document.getElementById('stat-max-loc').innerText = `Location: ${lat.toFixed(2)}°N, ${lon.toFixed(2)}°E`;
    
    // Enable Locate Button if max rainfall is greater than 0
    const focusMaxBtn = document.getElementById('focus-max-btn');
    if (data.stats.max_rainfall > 0) {
        focusMaxBtn.removeAttribute('disabled');
    } else {
        focusMaxBtn.setAttribute('disabled', 'true');
    }
    
    // 2. Render Rainfall Grid Overlay on Map
    renderRainfallOverlay(data);
    
    // 3. Update Distribution Chart
    updateChart(data);

    // 4. Update debug/status overlay (helps when embedded)
    updateDebugBox(data);
}

// Small visible debug/status box on the map for quick verification
function updateDebugBox(data) {
    let box = document.getElementById('debug-box');
    if (!box) {
        box = document.createElement('div');
        box.id = 'debug-box';
        box.style.position = 'absolute';
        box.style.top = '12px';
        box.style.right = '12px';
        box.style.zIndex = 3000;
        box.style.background = 'rgba(0,0,0,0.6)';
        box.style.color = 'white';
        box.style.padding = '8px 10px';
        box.style.borderRadius = '8px';
        box.style.fontSize = '12px';
        box.style.fontFamily = 'Inter, sans-serif';
        box.style.boxShadow = '0 6px 18px rgba(0,0,0,0.6)';
        document.querySelector('.map-container').appendChild(box);
    }

    const date = data.date || '(unknown)';
    const mean = data.stats?.mean_rainfall ?? '--';
    const max = data.stats?.max_rainfall ?? '--';
    box.innerText = `Date: ${date} — Mean: ${mean} mm — Max: ${max} mm`;
}

// Render the 2D grid onto a canvas and overlay it on Leaflet
function renderRainfallOverlay(data) {
    const rows = data.latitudes.length;     // 129
    const cols = data.longitudes.length;    // 135
    const rainfall = data.rainfall;
    
    // We will upscale the grid using bilinear interpolation to make it look smooth and professional
    const upscaleFactor = 4; // 4x resolution
    const newRows = rows * upscaleFactor;
    const newCols = cols * upscaleFactor;
    
    // Create off-screen canvas
    const canvas = document.createElement('canvas');
    canvas.width = newCols;
    canvas.height = newRows;
    const ctx = canvas.getContext('2d');
    const imgData = ctx.createImageData(newCols, newRows);
    
    // Populate pixels using bilinear interpolation
    for (let y = 0; y < newRows; y++) {
        // Map canvas y (0 to newRows-1) to NetCDF row index (rows-1 down to 0)
        const py = ((newRows - 1 - y) / (newRows - 1)) * (rows - 1);
        const y0 = Math.floor(py);
        const y1 = Math.min(y0 + 1, rows - 1);
        const dy = py - y0;
        
        for (let x = 0; x < newCols; x++) {
            // Map canvas x (0 to newCols-1) to NetCDF col index (0 to cols-1)
            const px = (x / (newCols - 1)) * (cols - 1);
            const x0 = Math.floor(px);
            const x1 = Math.min(x0 + 1, cols - 1);
            const dx = px - x0;
            
            const v00 = rainfall[y0][x0];
            const v01 = rainfall[y0][x1];
            const v10 = rainfall[y1][x0];
            const v11 = rainfall[y1][x1];
            
            const pixelIdx = (y * newCols + x) * 4;
            
            // If any of the 4 corners is ocean (-1), we treat this pixel as ocean or use nearest neighbor
            if (v00 === -1.0 || v01 === -1.0 || v10 === -1.0 || v11 === -1.0) {
                const nearestY = Math.round(py);
                const nearestX = Math.round(px);
                const nearestVal = rainfall[nearestY][nearestX];
                
                if (nearestVal === -1.0) {
                    // Transparent
                    imgData.data[pixelIdx] = 0;
                    imgData.data[pixelIdx + 1] = 0;
                    imgData.data[pixelIdx + 2] = 0;
                    imgData.data[pixelIdx + 3] = 0;
                    continue;
                }
            }
            
            // Bilinear interpolation for the rainfall value
            let val;
            if (v00 === -1.0 || v01 === -1.0 || v10 === -1.0 || v11 === -1.0) {
                // If some corners are masked, just use the nearest neighbor to avoid bleeding ocean values
                const nearestY = Math.round(py);
                const nearestX = Math.round(px);
                val = rainfall[nearestY][nearestX];
            } else {
                val = (1 - dy) * ((1 - dx) * v00 + dx * v01) + dy * ((1 - dx) * v10 + dx * v11);
            }
            
            // Find color based on rainfall value
            const colorObj = getPixelColor(val);
            imgData.data[pixelIdx] = colorObj.r;
            imgData.data[pixelIdx + 1] = colorObj.g;
            imgData.data[pixelIdx + 2] = colorObj.b;
            imgData.data[pixelIdx + 3] = colorObj.a;
        }
    }
    
    ctx.putImageData(imgData, 0, 0);
    const dataURL = canvas.toDataURL();
    
    // Bounding Box calculations:
    // Center of bottom-left cell: 6.5N, 66.5E
    // Center of top-right cell: 38.5N, 100.0E
    // Cell size is 0.25, so outer bounds are:
    // Lat: 6.5 - 0.125 = 6.375 to 38.5 + 0.125 = 38.625
    // Lon: 66.5 - 0.125 = 66.375 to 100.0 + 0.125 = 100.125
    const bounds = [
        [6.375, 66.375],
        [38.625, 100.125]
    ];
    
    // Remove existing layer if any
    if (rainfallLayer) {
        map.removeLayer(rainfallLayer);
    }
    
    // Add new image overlay
    rainfallLayer = L.imageOverlay(dataURL, bounds, {
        opacity: 0.8,
        interactive: false // We capture hover events on the map itself for speed
    }).addTo(map);
}

// Get RGBA pixel color for a rainfall value
function getPixelColor(val) {
    for (const bin of RAINFALL_COLORS) {
        if (val <= bin.limit) {
            return bin.color;
        }
    }
    return RAINFALL_COLORS[RAINFALL_COLORS.length - 1].color;
}

// Get text category and color badge class for hover info card
function getRainfallCategory(val) {
    if (val === -1.0) return { name: "No Data", class: "cat-nodata", color: "#64748b" };
    if (val <= 0.1) return { name: "No Rain", class: "cat-none", color: "#334155" };
    if (val <= 2.5) return { name: "Light", class: "cat-light", color: "#06b6d4" };
    if (val <= 7.5) return { name: "Moderate", class: "cat-moderate", color: "#0ea5e9" };
    if (val <= 19.0) return { name: "Rather Heavy", class: "cat-rheavy", color: "#0284c7" };
    if (val <= 35.5) return { name: "Heavy", class: "cat-heavy", color: "#0369a1" };
    if (val <= 64.5) return { name: "Very Heavy", class: "cat-vheavy", color: "#1d4ed8" };
    if (val <= 124.5) return { name: "Ext. Heavy", class: "cat-eheavy", color: "#7c3aed" };
    return { name: "Torrential", class: "cat-torrential", color: "#dc2626" };
}

// Handle Map Mouse Hovering
function handleMapHover(e) {
    if (!currentRainfallData) return;
    
    const lat = e.latlng.lat;
    const lng = e.latlng.lng;
    
    // Calculate 0.25x0.25 grid cell index
    // Grids are centered at 6.5, 6.75, ... and 66.5, 66.75, ...
    const row = Math.round((lat - 6.5) / 0.25);
    const col = Math.round((lng - 66.5) / 0.25);
    
    const rows = currentRainfallData.latitudes.length;
    const cols = currentRainfallData.longitudes.length;
    
    const hoverCard = document.getElementById('hover-card');
    
    if (row >= 0 && row < rows && col >= 0 && col < cols) {
        const val = currentRainfallData.rainfall[row][col];
        
        if (val !== -1.0) {
            // Valid land point
            const cellLat = 6.5 + row * 0.25;
            const cellLng = 66.5 + col * 0.25;
            const cat = getRainfallCategory(val);
            
            // Show hover card and update values
            hoverCard.classList.remove('hidden');
            document.getElementById('hover-coords').innerText = `${cellLat.toFixed(2)}°N, ${cellLng.toFixed(2)}°E`;
            document.getElementById('hover-val').innerHTML = `${val.toFixed(1)} <span class="unit">mm</span>`;
            
            const catBadge = document.getElementById('hover-category');
            catBadge.innerText = cat.name;
            catBadge.style.backgroundColor = cat.color;
            catBadge.style.color = '#ffffff';
            
            // Update Highlight Rectangle
            const rectBounds = [
                [cellLat - 0.125, cellLng - 0.125],
                [cellLat + 0.125, cellLng + 0.125]
            ];
            
            if (hoverRect) {
                hoverRect.setBounds(rectBounds);
            } else {
                hoverRect = L.rectangle(rectBounds, {
                    color: '#ffffff',
                    weight: 1.5,
                    fillColor: 'transparent',
                    interactive: false
                }).addTo(map);
            }
            return;
        }
    }
    
    // If not hovering on a valid grid point, hide card and rectangle
    hideHoverCardAndRect();
}

function handleMapMouseOut() {
    hideHoverCardAndRect();
}

function hideHoverCardAndRect() {
    const hoverCard = document.getElementById('hover-card');
    hoverCard.classList.add('hidden');
    if (hoverRect) {
        map.removeLayer(hoverRect);
        hoverRect = null;
    }
}

// Center Map on the Location of Maximum Rainfall
function centerOnMaxRainfall() {
    if (!currentRainfallData) return;
    
    const lat = currentRainfallData.stats.max_location.latitude;
    const lon = currentRainfallData.stats.max_location.longitude;
    
    map.setView([lat, lon], 8);
    
    // Draw a temporary pulsing circle marker at the location
    const tempCircle = L.circleMarker([lat, lon], {
        color: '#ff4d4d',
        fillColor: '#ff4d4d',
        fillOpacity: 0.5,
        radius: 12
    }).addTo(map);
    
    // Remove it after 2 seconds
    setTimeout(() => {
        map.removeLayer(tempCircle);
    }, 2000);
}

// Update Chart.js Distribution Chart
function updateChart(data) {
    const rainfall = data.rainfall;
    
    // Count grid cells in categories
    let counts = {
        noRain: 0,
        light: 0,
        moderate: 0,
        heavy: 0,
        extreme: 0
    };
    
    for (let r = 0; r < rainfall.length; r++) {
        for (let c = 0; c < rainfall[r].length; c++) {
            const val = rainfall[r][c];
            if (val === -1.0) continue; // Skip ocean
            
            if (val <= 0.1) counts.noRain++;
            else if (val <= 2.5) counts.light++;
            else if (val <= 7.5) counts.moderate++;
            else if (val <= 35.5) counts.heavy++;
            else counts.extreme++;
        }
    }
    
    const chartData = [counts.noRain, counts.light, counts.moderate, counts.heavy, counts.extreme];
    const labels = ['No Rain', 'Light (0.1-2.5 mm)', 'Moderate (2.5-7.5 mm)', 'Heavy (7.5-35.5 mm)', 'Extreme (>35.5 mm)'];
    const colors = [
        '#1e293b',  // Dark slate (No rain)
        '#06b6d4',  // Cyan (Light)
        '#0ea5e9',  // Sky (Moderate)
        '#0284c7',  // Blue (Heavy)
        '#dc2626'   // Red (Extreme)
    ];
    
    if (distributionChart) {
        distributionChart.data.datasets[0].data = chartData;
        distributionChart.update();
    } else {
        const ctx = document.getElementById('distribution-chart').getContext('2d');
        distributionChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: chartData,
                    backgroundColor: colors,
                    borderWidth: 1,
                    borderColor: 'rgba(255, 255, 255, 0.05)'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false // We hide legend in chart and rely on tooltips due to small space
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const val = context.raw;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const percentage = ((val / total) * 100).toFixed(1);
                                return `${context.label}: ${val} cells (${percentage}%)`;
                            }
                        }
                    }
                },
                cutout: '65%'
            }
        });
    }
}

// Timeline Animation Functions
function toggleTimelineAnimation() {
    const playBtn = document.getElementById('play-btn');
    
    if (isPlaying) {
        stopTimelineAnimation();
    } else {
        startTimelineAnimation();
    }
}

function startTimelineAnimation() {
    isPlaying = true;
    const playBtn = document.getElementById('play-btn');
    playBtn.classList.add('playing');
    playBtn.innerHTML = `<i data-lucide="pause"></i><span>Pause Animation</span>`;
    lucide.createIcons();
    
    const speedRange = document.getElementById('speed-range');
    const delay = parseInt(speedRange.value);
    
    // Set interval to change date
    animationInterval = setInterval(() => {
        changeDate(1);
    }, delay);
    
    // Update interval dynamically if speed range slider moves
    speedRange.addEventListener('input', handleSpeedChange);
}

function stopTimelineAnimation() {
    isPlaying = false;
    const playBtn = document.getElementById('play-btn');
    playBtn.classList.remove('playing');
    playBtn.innerHTML = `<i data-lucide="play"></i><span>Animate Timeline</span>`;
    lucide.createIcons();
    
    clearInterval(animationInterval);
    animationInterval = null;
    
    const speedRange = document.getElementById('speed-range');
    speedRange.removeEventListener('input', handleSpeedChange);
}

function handleSpeedChange() {
    if (!isPlaying) return;
    clearInterval(animationInterval);
    const speedRange = document.getElementById('speed-range');
    const delay = parseInt(speedRange.value);
    animationInterval = setInterval(() => {
        changeDate(1);
    }, delay);
}

// Show/Hide Loading Overlay
function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    if (show) {
        overlay.classList.remove('hidden');
    } else {
        overlay.classList.add('hidden');
    }
}
