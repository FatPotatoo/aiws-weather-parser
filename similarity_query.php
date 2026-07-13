<?php
$result = null;
$error = null;
$query_date = '';

// Handle Date Search and Analysis
if (isset($_POST['query_date'])) {
    $query_date = trim($_POST['query_date']);
    
    if (empty($query_date)) {
        $error = 'Please select a date.';
    } elseif (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $query_date)) {
        $error = 'Invalid date format. Use YYYY-MM-DD.';
    } else {
        // Execute python similarity script by passing the target date
        $py_script = __DIR__ . '/fireworks-weather-extractor/query_similar.py';
        $escaped_script = escapeshellarg($py_script);
        $escaped_date = escapeshellarg($query_date);
        
        $command = "python $escaped_script --date $escaped_date 2>&1";
        exec($command, $output, $return_var);
        
        $output_str = implode("\n", $output);
        if ($return_var !== 0) {
            $error = 'Execution failed. Code: ' . $return_var . '. Output: ' . htmlspecialchars($output_str);
        } else {
            $result = json_decode($output_str, true);
            if (json_last_error() !== JSON_ERROR_NONE) {
                $error = 'Failed to parse script output. Raw response: ' . htmlspecialchars($output_str);
                $result = null;
            } elseif (isset($result['error'])) {
                $error = $result['error'];
                $result = null;
            }
        }
    }
}
?>

<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Weather Similarity Query</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
  <style>
    /* Custom loader styling */
    .loader {
      border-top-color: #3b82f6;
      -webkit-animation: spinner 1.5s linear infinite;
      animation: spinner 1.5s linear infinite;
    }
    @-webkit-keyframes spinner {
      0% { -webkit-transform: rotate(0deg); }
      100% { -webkit-transform: rotate(360deg); }
    }
    @keyframes spinner {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
  </style>
</head>
<body class="bg-gray-100 min-h-screen flex">

<!-- Sidebar -->
<button onclick="toggleSidebar()" class="text-3xl m-4 z-50 fixed top-4 left-4 md:hidden">☰</button>
<div id="sidebar" class="fixed top-0 left-0 h-full w-64 bg-blue-900 text-white p-6 shadow-lg transform -translate-x-full md:translate-x-0 transition-transform duration-300 z-40">
  <div class="flex justify-between items-center mb-6">
    <h2 class="text-xl font-bold">Navigation</h2>
    <button class="md:hidden text-white text-2xl" onclick="toggleSidebar()">×</button>
  </div>
  <nav class="flex flex-col space-y-3">
    <a href="homepage.html" class="hover:underline block">🏠 Homepage</a>
    <a href="index.php" class="hover:underline block">✍️ Data Entry</a>
    <a href="view_data.php" class="hover:underline block">📄 View Data</a>
    <a href="similarity_query.php" class="hover:underline font-semibold text-yellow-300 block">🔍 Similarity Query</a>
  </nav>
</div>

<!-- Main Content Area -->
<main class="flex-1 p-8 md:ml-64">
  <div class="max-w-4xl mx-auto">
    <div class="text-center mb-8 text-black">
      <h1 class="text-4xl font-bold text-blue-900 mb-2">
        <i class="fas fa-search-location mr-2"></i>
        Historical Weather Similarity Query
      </h1>
      <p class="text-gray-600">Find historical weather records matching a specific date's weather pattern layout using TF-IDF and Cosine Similarity</p>
    </div>

    <!-- Alert Messages -->
    <?php if ($error): ?>
      <div class="p-4 mb-6 rounded-lg bg-red-100 text-red-800 border-l-4 border-red-600">
        <i class="fas fa-exclamation-triangle mr-2"></i>
        <strong>Error:</strong> <?php echo htmlspecialchars($error); ?>
      </div>
    <?php endif; ?>

    <!-- Query Panel -->
    <div class="bg-white rounded-lg shadow-lg p-6 mb-6 text-black">
      <h2 class="text-xl font-bold text-gray-800 mb-4">
        <i class="fas fa-calendar-alt mr-2 text-blue-600"></i>
        Select Weather Pattern Date
      </h2>
      <form method="POST" id="queryForm" onsubmit="showLoading()" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">Target Query Date</label>
          <input type="date" name="query_date" required min="2020-01-01" max="2025-12-31"
                 value="<?php echo htmlspecialchars($query_date); ?>"
                 class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-black">
          <p class="mt-1 text-xs text-gray-400">Select any day between 2020 and 2025. The system will look up this day's weather system layout and compare it with the rest of the database.</p>
        </div>
        <div class="flex justify-end">
          <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium flex items-center">
            <i class="fas fa-search mr-2"></i> Find Similar Days
          </button>
        </div>
      </form>
    </div>

    <!-- Loading Animation -->
    <div id="loadingOverlay" class="hidden bg-white rounded-lg shadow-lg p-12 text-center flex flex-col items-center">
      <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-16 w-16 mb-4"></div>
      <h3 class="text-lg font-bold text-gray-800">Analyzing Weather Similarity Profile...</h3>
      <p class="text-sm text-gray-500 mt-2 max-w-md">Our backend engine is retrieving the weather layout for the selected date and executing a mathematical similarity lookup across the rest of the database. This takes only 1-2 seconds.</p>
    </div>

    <!-- Query Results Display -->
    <?php if ($result): ?>
      <div id="resultsArea" class="space-y-6 text-black">
        
        <!-- Source Extracted Data -->
        <div class="bg-blue-50 border-l-4 border-blue-600 rounded-lg shadow p-6">
          <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-bold text-blue-900">
              <i class="fas fa-clipboard-check mr-2"></i>
              Query Profile (Selected Date)
            </h2>
            <span class="bg-blue-600 text-white px-3 py-1 rounded-full text-sm font-semibold">
              Date: <?php echo htmlspecialchars($result['query_date']); ?>
            </span>
          </div>
          <div class="grid grid-cols-1 gap-3">
            <?php foreach ($result['query_extracted'] as $sys): ?>
              <div class="bg-white p-3 rounded shadow-sm border">
                <div class="font-bold text-gray-800 text-md"><?php echo htmlspecialchars($sys['system']); ?></div>
                <div class="text-sm text-gray-600 mt-1">
                  <span class="inline-block mr-4"><i class="fas fa-layer-group text-blue-400 mr-1"></i> <?php echo htmlspecialchars($sys['pressure'] ?: 'Surface'); ?></span>
                  <span><i class="fas fa-map-marker-alt text-red-400 mr-1"></i> <?php echo htmlspecialchars(implode(', ', $sys['subdivisions']) ?: 'None/External'); ?></span>
                </div>
              </div>
            <?php endforeach; ?>
          </div>
        </div>

        <!-- Top KNN Matches -->
        <div>
          <h2 class="text-2xl font-bold text-gray-800 mb-4">
            <i class="fas fa-list-ol mr-2 text-green-600"></i>
            Top 5 Most Similar Historical Days
          </h2>
          <div class="space-y-4">
            <?php foreach ($result['top_matches'] as $rank => $match): ?>
              <div class="bg-white rounded-lg shadow-md hover:shadow-lg transition overflow-hidden border">
                
                <!-- Match Header -->
                <div class="p-4 bg-gray-50 border-b flex justify-between items-center flex-wrap gap-2">
                  <div class="flex items-center gap-3">
                    <span class="h-8 w-8 rounded-full bg-blue-900 text-white flex items-center justify-center font-bold text-sm">
                      #<?php echo $rank + 1; ?>
                    </span>
                    <span class="font-bold text-lg text-gray-800"><?php echo htmlspecialchars($match['date']); ?></span>
                    <a href="view_data.php?date_filter=<?php echo urlencode($match['date']); ?>" target="_blank"
                       class="text-blue-600 hover:text-blue-800 text-xs font-semibold hover:underline">
                      <i class="fas fa-external-link-alt mr-1"></i>View Full Data
                    </a>
                  </div>
                  
                  <!-- Similarity Score / Confidence Meter -->
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-semibold text-gray-500">Similarity Match:</span>
                    <span class="text-lg font-extrabold text-blue-700"><?php echo $match['score']; ?>%</span>
                  </div>
                </div>

                <!-- Similarity Score Progress Bar -->
                <div class="w-full bg-gray-200 h-2">
                  <div class="bg-blue-600 h-2 transition-all duration-500" style="width: <?php echo $match['score']; ?>%"></div>
                </div>

                <!-- Systems observed on that day -->
                <div class="p-5">
                  <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Systems Observed on this Day:</h4>
                  <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <?php foreach ($match['systems'] as $sys): ?>
                      <div class="p-3 bg-gray-50 rounded border text-sm">
                        <div class="font-bold text-gray-700"><?php echo htmlspecialchars($sys['system']); ?></div>
                        <div class="text-xs text-gray-500 mt-1">
                          <span class="mr-3"><i class="fas fa-layer-group text-blue-400 mr-1"></i> <?php echo htmlspecialchars($sys['pressure'] ?: 'Surface'); ?></span>
                          <span><i class="fas fa-map-marker-alt text-red-400 mr-1"></i> <?php echo htmlspecialchars(implode(', ', $sys['subdivisions']) ?: 'None/External'); ?></span>
                        </div>
                      </div>
                    <?php endforeach; ?>
                  </div>
                </div>

              </div>
            <?php endforeach; ?>
          </div>
        </div>

      </div>
    <?php endif; ?>
  </div>
</main>

<script>
  function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('-translate-x-full');
  }

  function showLoading() {
    // Hide results if visible
    const resultsArea = document.getElementById('resultsArea');
    if (resultsArea) {
      resultsArea.classList.add('hidden');
    }
    // Show loader
    const loader = document.getElementById('loadingOverlay');
    loader.classList.remove('hidden');
  }
</script>
</body>
</html>
