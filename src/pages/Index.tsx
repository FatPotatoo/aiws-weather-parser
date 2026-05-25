
import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Calendar, Database, Download, Eye, Plus, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import DateSelector from '@/components/DateSelector';
import WeatherSystemForm from '@/components/WeatherSystemForm';
import DataViewer from '@/components/DataViewer';

export interface WeatherSystemData {
  system: string;
  levels: string[];
  subdivisions: string[];
}

export interface WeatherEntry {
  id: string;
  date: string;
  systems: WeatherSystemData[];
  createdAt: string;
}

const Index = () => {
  const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());
  const [weatherSystems, setWeatherSystems] = useState<WeatherSystemData[]>(
    Array(5).fill(null).map(() => ({
      system: '',
      levels: [],
      subdivisions: []
    }))
  );
  const [showDataViewer, setShowDataViewer] = useState(false);
  const [savedEntries, setSavedEntries] = useState<WeatherEntry[]>([]);

  const handleSystemChange = (index: number, data: WeatherSystemData) => {
    const newSystems = [...weatherSystems];
    newSystems[index] = data;
    setWeatherSystems(newSystems);
  };

  const addWeatherSystem = () => {
    setWeatherSystems(prev => [...prev, {
      system: '',
      levels: [],
      subdivisions: []
    }]);
  };

  const removeWeatherSystem = (index: number) => {
    if (weatherSystems.length > 1) {
      setWeatherSystems(prev => prev.filter((_, i) => i !== index));
    } else {
      toast.error('At least one weather system is required');
    }
  };

  const handleSubmit = () => {
    if (!selectedDate) {
      toast.error('Please select a date');
      return;
    }

    const filledSystems = weatherSystems.filter(
      system => system.system || system.levels.length > 0 || system.subdivisions.length > 0
    );

    if (filledSystems.length === 0) {
      toast.error('Please fill at least one weather system');
      return;
    }

    const newEntry: WeatherEntry = {
      id: Date.now().toString(),
      date: selectedDate.toISOString().split('T')[0],
      systems: filledSystems,
      createdAt: new Date().toISOString()
    };

    setSavedEntries(prev => [...prev, newEntry]);
    
    // Reset form
    setWeatherSystems(Array(5).fill(null).map(() => ({
      system: '',
      levels: [],
      subdivisions: []
    })));
    
    toast.success('Weather data saved successfully!');
  };

  const exportToCSV = () => {
    if (savedEntries.length === 0) {
      toast.error('No data to export');
      return;
    }

    const maxSystems = Math.max(...savedEntries.map(entry => entry.systems.length));
    const headers = ['Date'];
    
    for (let i = 0; i < maxSystems; i++) {
      headers.push(`System ${i + 1}`, `Levels ${i + 1}`, `Subdivisions ${i + 1}`);
    }
    headers.push('Created At');

    const csvContent = [
      headers.join(','),
      ...savedEntries.map(entry => {
        const row = [entry.date];
        for (let i = 0; i < maxSystems; i++) {
          const system = entry.systems[i] || { system: '', levels: [], subdivisions: [] };
          row.push(
            system.system || '',
            system.levels.join(';') || '',
            system.subdivisions.join(';') || ''
          );
        }
        row.push(entry.createdAt);
        return row.join(',');
      })
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `weather-data-${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    
    toast.success('Data exported successfully!');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-sky-100 p-4">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2 flex items-center justify-center gap-3">
            <Database className="text-blue-600" />
            IMD Weather Data Management System
          </h1>
          <p className="text-gray-600 text-lg">Comprehensive weather systems data collection and management</p>
        </div>

        {!showDataViewer ? (
          <div className="space-y-6">
            <Card className="shadow-lg border-0 bg-white/80 backdrop-blur-sm">
              <CardHeader className="bg-gradient-to-r from-blue-600 to-sky-600 text-white rounded-t-lg">
                <CardTitle className="flex items-center gap-2">
                  <Calendar className="w-5 h-5" />
                  Date Selection
                </CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                <DateSelector selectedDate={selectedDate} onDateChange={setSelectedDate} />
              </CardContent>
            </Card>

            <div className="grid gap-6">
              {weatherSystems.map((system, index) => (
                <div key={index} className="relative">
                  <WeatherSystemForm
                    systemNumber={index + 1}
                    data={system}
                    onChange={(data) => handleSystemChange(index, data)}
                  />
                  {weatherSystems.length > 1 && (
                    <Button
                      onClick={() => removeWeatherSystem(index)}
                      variant="destructive"
                      size="sm"
                      className="absolute top-4 right-4 z-10"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>

            <div className="flex justify-center mb-6">
              <Button 
                onClick={addWeatherSystem}
                variant="outline"
                className="border-green-600 text-green-600 hover:bg-green-50"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Another Weather System
              </Button>
            </div>

            <div className="flex flex-wrap gap-4 justify-center">
              <Button 
                onClick={handleSubmit}
                size="lg"
                className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-8 py-3"
              >
                <Database className="w-5 h-5 mr-2" />
                Save Weather Data
              </Button>
              
              <Button 
                onClick={() => setShowDataViewer(true)}
                size="lg"
                variant="outline"
                className="border-blue-600 text-blue-600 hover:bg-blue-50 px-8 py-3"
              >
                <Eye className="w-5 h-5 mr-2" />
                View Data ({savedEntries.length})
              </Button>
              
              <Button 
                onClick={exportToCSV}
                size="lg"
                variant="outline"
                className="border-purple-600 text-purple-600 hover:bg-purple-50 px-8 py-3"
                disabled={savedEntries.length === 0}
              >
                <Download className="w-5 h-5 mr-2" />
                Export CSV
              </Button>
            </div>
          </div>
        ) : (
          <DataViewer 
            entries={savedEntries} 
            onBack={() => setShowDataViewer(false)}
            onDelete={(id) => setSavedEntries(prev => prev.filter(entry => entry.id !== id))}
          />
        )}
      </div>
    </div>
  );
};

export default Index;
