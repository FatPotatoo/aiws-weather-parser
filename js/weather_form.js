
const weatherSystems = [
  //  Cyclonic Circulations
  "Cyclonic Circulation (CYCIR)",
  "Low Pressure (L) with associated CYCIR",
  "Well Marked Low Pressure Area (WML) with associated CYCIR",
  "Induced Cyclonic Circulation",
  "Induced Low",
  "Low-Level Cyclonic Circulation",
  "Mid-Level Cyclonic Circulation",
  "Upper-Level Cyclonic Circulation",
  
  // Western Disturbances & Related Systems
  "Western Disturbances (WD)",
  "Western Depression",

  //  Cyclonic Storms (by intensity)
  "Depression (D)",
  "Deep Depression (DD)",
  "Cyclonic Storm (CS) : 63 to 88 km/h",
  "Severe Cyclonic Storm (SCS) : 89 to 117 km/h",
  "Very Severe Cyclonic Storm (VSCS) : 118 to 165 km/h",
  "Extremely Severe Cyclonic Storm (ESCS) : 166 to 220 km/h",
  "Super Cyclonic Storm (SuCS) : ≥ 221 km/h",

  //  Troughs and Monsoon Features
  "Trough",
  "Easterly Trough",
  "Westerly Trough",
  "Offshore Trough",
  "At Surface Trough",
  "Mean Sea Level Trough",
  "Monsoon Trough with Extension and Tilt",

  
];

const pressureLevels = [
    "Surface",
    "925 hPa",
    "850 hPa",
    "700 hPa",
    "600 hPa",
    "500 hPa",
    "400 hpa",
    "300 hpa",
    "200 hPa",
    "100 hPa"
];

const subdivisions = [
    "Andaman & Nicobar Islands",
    "Arunachal Pradesh",
    "Assam & Meghalaya",
    "Bihar",
    "Chhattisgarh",
    "Coastal Andhra Pradesh",
    "Coastal Karnataka",
    "East Madhya Pradesh",
    "East Rajasthan",
    "East Uttar Pradesh",
    "Gangetic West Bengal",
    "Gujarat Region",
    "Haryana, Chandigarh & Delhi",
    "Himachal Pradesh",
    "Jammu & Kashmir",
    "Jharkhand",
    "Kerala",
    "Konkan & Goa",
    "Lakshadweep",
    "Madhya Maharashtra",
    "Marathwada",
    "Nagaland, Manipur, Mizoram & Tripura",
    "North Interior Karnataka",
    "Odisha",
    "Punjab",
    "Rayalaseema",
    "Saurashtra & Kutch",
    "Sikkim",
    "South Interior Karnataka",
    "Sub-Himalayan West Bengal & Sikkim",
    "Tamil Nadu & Puducherry",
    "Telangana",
    "Uttarakhand",
    "Vidarbha",
    "West Madhya Pradesh",
    "West Rajasthan",
    "West Uttar Pradesh",
    "NW Arabian Sea",
    "NE Arabian Sea",
    "WC Arabian Sea",
    "EC Arabian Sea",
    "SW Arabian Sea",
    "SE Arabian Sea",
    "NW Bay",
    "NE Bay",
    "WC Bay",
    "EC Bay",
    "SW Bay",
    "SE Bay",
    "N Andaman Sea",
    "S Andaman Sea"
];

let systemCounter = 0;

function createWeatherSystemHTML(systemNumber) {
    return `
        <div class="weather-system bg-gray-50 rounded-lg p-6 mb-4 border border-gray-200" data-system="${systemNumber}">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-semibold text-indigo-700">
                    <i class="fas fa-cloud mr-2"></i>
                    Weather System ${systemNumber}
                </h3>
                <button type="button" class="remove-system text-red-600 hover:text-red-800" data-system="${systemNumber}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>

            <!-- Weather System Selection -->
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    <i class="fas fa-cloud-rain mr-2"></i>
                    Weather System Type
                </label>
                <select name="weather_systems[${systemNumber}][system]" class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500">
                    <option value="">Select a weather system</option>
                    ${weatherSystems.map(system => `<option value="${system}">${system}</option>`).join('')}
                </select>
            </div>

            <!-- Pressure Levels -->
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    <i class="fas fa-layer-group mr-2"></i>
                    Pressure Levels (Multiple Selection)
                </label>
                <div class="grid grid-cols-2 md:grid-cols-3 gap-2 max-h-32 overflow-y-auto border rounded-lg p-3 bg-white">
                    ${pressureLevels.map(level => `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-blue-50 p-1 rounded">
                            <input type="checkbox" name="weather_systems[${systemNumber}][levels][]" value="${level}" class="text-blue-600">
                            <span class="text-sm">${level}</span>
                        </label>
                    `).join('')}
                </div>
            </div>

            <!-- Subdivisions -->
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-2">
                    <i class="fas fa-map-marker-alt mr-2"></i>
                    Meteorological Subdivisions (Multiple Selection)
                </label>
                <div class="max-h-48 overflow-y-auto border rounded-lg p-3 bg-white">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-1">
                        ${subdivisions.map(subdivision => `
                            <label class="flex items-center space-x-2 cursor-pointer hover:bg-green-50 p-1 rounded text-sm">
                                <input type="checkbox" name="weather_systems[${systemNumber}][subdivisions][]" value="${subdivision}" class="text-green-600">
                                <span>${subdivision}</span>
                            </label>
                        `).join('')}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function addWeatherSystem() {
    systemCounter++;
    const container = document.getElementById('weatherSystemsContainer');
    const systemHTML = createWeatherSystemHTML(systemCounter);
    container.insertAdjacentHTML('beforeend', systemHTML);
    
    // Add remove event listener
    const removeBtn = container.querySelector(`[data-system="${systemCounter}"] .remove-system`);
    removeBtn.addEventListener('click', function() {
        const systemDiv = this.closest('.weather-system');
        systemDiv.remove();
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Add initial weather system
    addWeatherSystem();
    
    // Add event listener for adding more systems
    document.getElementById('addSystemBtn').addEventListener('click', addWeatherSystem);
});
