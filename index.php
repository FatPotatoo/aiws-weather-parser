
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weather Data Management System - IMD</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-gradient-to-br from-blue-50 to-sky-100 min-h-screen">
<!-- Sidebar Toggle Button (☰ icon) -->
<button onclick="document.getElementById('sidebar').classList.toggle('hidden')" class="text-3xl m-4 z-50 fixed top-4 left-4">
    &#9776;
</button>

<!-- Sidebar Menu -->
<div id="sidebar" class="hidden fixed top-0 left-0 h-full w-48 bg-blue-900 text-white p-6 pt-16 shadow-lg z-40">
    <!-- Empty space instead of "Navigation" heading -->
    <div class="h-8"></div> <!-- creates vertical space without text -->

    <!-- Navigation Links -->
    <ul class="space-y-4">
        <li><a href="homepage.html" class="hover:underline">🏠 Home</a></li>
        <li><a href="index.php" class="hover:underline">📝 Data Entry</a></li>
        <li><a href="view_data.php" class="hover:underline">📊 View Data</a></li>
    </ul>
</div>


    <div class="container mx-auto px-4 py-8">
        <div class="text-center mb-8">
            <h1 class="text-4xl font-bold text-blue-800 mb-2">
                <i class="fas fa-cloud-sun mr-3"></i>
                Weather Data Management System
            </h1>
            <p class="text-gray-600">India Meteorological Department</p>
        </div>

        <div class="max-w-6xl mx-auto">
            <div class="bg-white rounded-lg shadow-lg p-6 mb-6">
                <div class="flex justify-between items-center mb-6">
                    <h2 class="text-2xl font-bold text-gray-800">
                        <i class="fas fa-calendar-plus mr-2"></i>
                        Add Weather Data Entry
                    </h2>
                    <a href="view_data.php" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg">
                        <i class="fas fa-eye mr-2"></i>
                        View Data
                    </a>
                </div>

                <form id="weatherForm" action="process_form.php" method="POST">
                    <!-- Date Selection -->
                    <div class="mb-6">
                        <label class="block text-sm font-medium text-gray-700 mb-2">
                            <i class="fas fa-calendar mr-2"></i>
                            Select Date for Weather Data Entry
                        </label>
                        <input type="date" name="entry_date" required 
                               class="w-60 p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500">
                    </div>

                    <!-- Weather Systems Container -->
                    <div id="weatherSystemsContainer">
                        <!-- Initial weather system will be added here by JavaScript -->
                    </div>

                    <div class="flex justify-between items-center mt-6">
                        <button type="button" id="addSystemBtn" 
                                class="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg">
                            <i class="fas fa-plus mr-2"></i>
                            Add Weather System
                        </button>
                        
                        <button type="submit" 
                                class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium">
                            <i class="fas fa-save mr-2"></i>
                            Save Weather Data
                        </button>
                    </div>
                </form>
            </div>
        </div>
    </div>

    <script src="js/weather_form.js"></script>
</body>
</html>
