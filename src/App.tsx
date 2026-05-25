import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import DataViewer from "@/components/DataViewer";
import { useState } from "react";

const queryClient = new QueryClient();

const App = () => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <div className="flex h-screen">
            {/* Sidebar */}
            <div
              className={`bg-gray-900 text-white w-64 p-4 space-y-4 transform transition-transform duration-300 ${
                isSidebarOpen ? "translate-x-0" : "-translate-x-full"
              } md:translate-x-0 fixed md:static z-10 h-full`}
            >
              <h1 className="text-xl font-bold mb-4">Navigation</h1>
              <nav className="space-y-2">
                <Link to="/" className="block hover:bg-gray-700 p-2 rounded">Homepage</Link>
                <Link to="/data-entry" className="block hover:bg-gray-700 p-2 rounded">Data Entry</Link>
                <Link to="/view" className="block hover:bg-gray-700 p-2 rounded">View Data</Link>
              </nav>
            </div>

            {/* Content Area */}
            <div className="flex-1 ml-0 md:ml-64">
              {/* Toggle Button */}
              <button
                className="md:hidden p-2 m-2 text-gray-900 bg-gray-200 rounded"
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              >
                ☰
              </button>
              <Routes>
                <Route path="/" element={<div className="p-4 text-center text-xl">Welcome to IMD Portal</div>} />
                <Route path="/data-entry" element={<Index />} />
                <Route path="/view" element={<DataViewer entries={[]} onBack={() => {}} onDelete={() => {}} />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </div>
          </div>
        </BrowserRouter>
      </TooltipProvider>
    </QueryClientProvider>
  );
};

export default App;

