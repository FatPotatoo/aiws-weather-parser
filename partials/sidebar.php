<!-- Sidebar Toggle Button -->
<button onclick="toggleSidebar()" class="text-3xl m-4 z-50 fixed top-4 left-4 md:hidden">
  ☰
</button>

<!-- Sidebar -->
<div id="sidebar" class="fixed top-0 left-0 h-full w-64 bg-blue-900 text-white p-6 shadow-lg transform -translate-x-full md:translate-x-0 transition-transform duration-300 z-40">
  <div class="flex justify-between items-center mb-6">
    <h2 class="text-xl font-bold">Navigation</h2>
    <button class="md:hidden text-white text-2xl" onclick="toggleSidebar()">×</button>
  </div>
  <nav class="flex flex-col space-y-3">
    <a href="homepage.html" onclick="toggleSidebarIfMobile()" class="hover:underline block">🏠 Home</a>
    <a href="index.php" onclick="toggleSidebarIfMobile()" class="hover:underline block">✍️ Data Entry</a>
    <a href="view_data.php" onclick="toggleSidebarIfMobile()" class="hover:underline block">📄 View Data</a>
  </nav>
</div>
