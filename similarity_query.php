<?php
$config_dir = __DIR__ . '/config';
$config_file = $config_dir . '/fireworks.json';

// Handle API Key Save
$message = '';
$message_type = '';
if (isset($_POST['save_api_key'])) {
    $api_key = trim($_POST['api_key'] ?? '');
    if (!file_exists($config_dir)) {
        mkdir($config_dir, 0777, true);
    }
    if (file_put_contents($config_file, json_encode(['FIREWORKS_API_KEY' => $api_key], JSON_PRETTY_PRINT))) {
        $message = 'API Key saved successfully!';
        $message_type = 'success';
    } else {
        $message = 'Failed to save API Key. Check write permissions on config/ directory.';
        $message_type = 'error';
    }
}

// Read current API Key for display
$current_key = '';
if (file_exists($config_file)) {
    $config_data = json_decode(file_get_contents($config_file), true);
    $current_key = $config_data['FIREWORKS_API_KEY'] ?? '';
}
// Masked version of key for security
$masked_key = $current_key ? substr($current_key, 0, 8) . '...' . substr($current_key, -4) : '';

$result = null;
$error = null;

// Handle File Upload and Analysis
if (isset($_FILES['bulletin_file']) && $_FILES['bulletin_file']['error'] == UPLOAD_ERR_OK) {
    $file_tmp = $_FILES['bulletin_file']['tmp_name'];
    $file_name = $_FILES['bulletin_file']['name'];
    $file_ext = strtolower(pathinfo($file_name, PATHINFO_EXTENSION));

    if ($file_ext !== 'docx') {
        $error = 'Only .docx files are supported.';
    } else {
        $upload_dir = __DIR__ . '/uploads';
        if (!file_exists($upload_dir)) {
            mkdir($upload_dir, 0777, true);
        }
        $target_file = $upload_dir . '/' . uniqid('bulletin_') . '.docx';
        if (move_uploaded_file($file_tmp, $target_file)) {
            // Execute python similarity script
            $py_script = __DIR__ . '/fireworks-weather-extractor/query_similar.py';
            $escaped_script = escapeshellarg($py_script);
            $escaped_file = escapeshellarg($target_file);
            
            // Set the environment variable just in case
            if ($current_key) {
                putenv("FIREWORKS_API_KEY=" . $current_key);
            }
            
            $command = "python $escaped_script $escaped_file 2>&1";
            exec($command, $output, $return_var);
            
            // Delete temp file
            if (file_exists($target_file)) {
                unlink($target_file);
            }
            
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
        } else {
            $error = 'Failed to move uploaded file.';
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
    <div class="text-center mb-8">
      <h1 class="text-4xl font-bold text-blue-900 mb-2">
        <i class="fas fa-search-location mr-2"></i>
        Advanced Weather Similarity Query
      </h1>
      <p class="text-gray-600">Find historical weather records matching a specific bulletin pattern using NLP (GLM 5.2) and KNN clustering</p>
    </div>

    <!-- Alert Messages -->
    <?php if ($message): ?>
      <div class="p-4 mb-6 rounded-lg <?php echo $message_type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'; ?>">
        <i class="fas <?php echo $message_type === 'success' ? 'fa-check-circle' : 'fa-exclamation-circle'; ?> mr-2"></i>
        <?php echo htmlspecialchars($message); ?>
      </div>
    <?php endif; ?>

    <?php if ($error): ?>
      <div class="p-4 mb-6 rounded-lg bg-red-100 text-red-800">
        <i class="fas fa-exclamation-triangle mr-2"></i>
        <strong>Error:</strong> <?php echo htmlspecialchars($error); ?>
      </div>
    <?php endif; ?>

    <!-- Collapsible API Configuration Panel -->
    <details class="bg-white rounded-lg shadow mb-6 overflow-hidden" <?php echo !$current_key ? 'open' : ''; ?>>
      <summary class="p-4 bg-gray-50 border-b font-medium text-gray-700 cursor-pointer hover:bg-gray-100 flex justify-between items-center">
        <span>
          <i class="fas fa-key mr-2 text-yellow-500"></i>
          Fireworks API Configuration
          <?php if ($current_key): ?>
            <span class="ml-2 text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full font-normal">Configured</span>
          <?php else: ?>
            <span class="ml-2 text-xs bg-red-200 text-red-800 px-2 py-0.5 rounded-full font-normal">Missing API Key</span>
          <?php endif; ?>
        </span>
        <i class="fas fa-chevron-down text-gray-400"></i>
      </summary>
      <div class="p-6">
        <form method="POST" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Fireworks API Key</label>
            <input type="password" name="api_key" placeholder="Paste FIREWORKS_API_KEY" required
                   class="w-full p-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-black"
                   value="<?php echo htmlspecialchars($current_key); ?>">
            <p class="mt-1 text-xs text-gray-400">This key is saved locally in config/fireworks.json and used by the background python extractor.</p>
          </div>
          <button type="submit" name="save_api_key" class="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium">
            Save Configuration
          </button>
        </form>
      </div>
    </details>

    <!-- Upload Panel -->
    <div class="bg-white rounded-lg shadow-lg p-6 mb-6">
      <h2 class="text-xl font-bold text-gray-800 mb-4">
        <i class="fas fa-file-upload mr-2 text-blue-600"></i>
        Upload Daily Weather Summary (.docx)
      </h2>
      <form method="POST" enctype="multipart/form-data" id="queryForm" onsubmit="showLoading()">
        <div class="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-500 transition-colors cursor-pointer" onclick="document.getElementById('fileInput').click()">
          <input type="file" name="bulletin_file" id="fileInput" class="hidden" accept=".docx" required onchange="updateFileName(this)">
          <i class="fas fa-file-word text-5xl text-blue-400 mb-3 block"></i>
          <span class="text-gray-700 font-medium block" id="uploadLabel">Drag & drop your weather summary file here, or click to browse</span>
          <span class="text-xs text-gray-400 mt-1 block">Only .docx files are supported. Analysis takes ~15 seconds.</span>
        </div>
        <div class="mt-4 flex justify-end">
          <button type="submit" class="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-medium flex items-center">
            <i class="fas fa-bolt mr-2"></i> Run Similarity Query
          </button>
        </div>
      </form>
    </div>

    <!-- Loading Animation -->
    <div id="loadingOverlay" class="hidden bg-white rounded-lg shadow-lg p-12 text-center flex flex-col items-center">
      <div class="loader ease-linear rounded-full border-4 border-t-4 border-gray-200 h-16 w-16 mb-4"></div>
      <h3 class="text-lg font-bold text-gray-800">Processing Weather Summary Bulletin...</h3>
      <p class="text-sm text-gray-500 mt-2 max-w-md">Our backend pipeline is extracting the weather systems with the Fireworks GLM 5.2 model and executing the KNN similarity query across your entire historical database. This will take about 10-15 seconds.</p>
    </div>

    <!-- Query Results Display -->
    <?php if ($result): ?>
      <div id="resultsArea" class="space-y-6">
        
        <!-- Source Extracted Data -->
        <div class="bg-blue-50 border-l-4 border-blue-600 rounded-lg shadow p-6">
          <div class="flex justify-between items-center mb-4">
            <h2 class="text-xl font-bold text-blue-900">
              <i class="fas fa-clipboard-check mr-2"></i>
              Extracted Profile (Target Bulletin)
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

  function updateFileName(input) {
    const label = document.getElementById('uploadLabel');
    if (input.files.length > 0) {
      label.textContent = "Selected: " + input.files[0].name;
      label.classList.add('text-blue-600');
    } else {
      label.textContent = "Drag & drop your weather summary file here, or click to browse";
      label.classList.remove('text-blue-600');
    }
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
