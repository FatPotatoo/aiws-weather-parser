
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Cloud, Layers, MapPin } from 'lucide-react';
import { WeatherSystemData } from '@/pages/Index';

interface WeatherSystemFormProps {
  systemNumber: number;
  data: WeatherSystemData;
  onChange: (data: WeatherSystemData) => void;
}

const weatherSystems = [
  "Low Pressure",
  "Depression",
  "Cyclonic Storm (CS) : 63–88 km/h",
  "Severe Cyclonic Storm (SCS) : 89–117 km/h",
  "Very Severe Cyclonic Storm (VSCS) : 118–165 km/h",
  "Extremely Severe Cyclonic Storm (ESCS) : 166–220 km/h",
  "Super Cyclonic Storm (SuCS) : ≥ 221 km/h",
  "Western Disturbances",
  "Easterly Trough",
  "Westerly Trough",
  "Offshore Trough",
  "Low-Level Cyclonic Circulation",
  "Mid-Level Cyclonic Circulation",
  "Upper-Level Cyclonic Circulation"
];

const pressureLevels = [
  "Surface",
  "925 hPa",
  "850 hPa",
  "700 hPa",
  "500 hPa",
  "200 hPa"
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

const WeatherSystemForm: React.FC<WeatherSystemFormProps> = ({ systemNumber, data, onChange }) => {
  const handleSystemChange = (system: string) => {
    onChange({ ...data, system });
  };

  const handleLevelToggle = (level: string) => {
    const newLevels = data.levels.includes(level)
      ? data.levels.filter(l => l !== level)
      : [...data.levels, level];
    onChange({ ...data, levels: newLevels });
  };

  const handleSubdivisionToggle = (subdivision: string) => {
    const newSubdivisions = data.subdivisions.includes(subdivision)
      ? data.subdivisions.filter(s => s !== subdivision)
      : [...data.subdivisions, subdivision];
    onChange({ ...data, subdivisions: newSubdivisions });
  };

  return (
    <Card className="shadow-lg border-0 bg-white/90 backdrop-blur-sm">
      <CardHeader className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-t-lg">
        <CardTitle className="flex items-center gap-2">
          <Cloud className="w-5 h-5" />
          Weather System {systemNumber}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-6 space-y-6">
        {/* Weather System Selection */}
        <div className="space-y-2">
          <Label className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Cloud className="w-4 h-4 text-indigo-600" />
            Weather System Type
          </Label>
          <Select value={data.system} onValueChange={handleSystemChange}>
            <SelectTrigger className="h-12">
              <SelectValue placeholder="Select a weather system" />
            </SelectTrigger>
            <SelectContent>
              {weatherSystems.map((system) => (
                <SelectItem key={system} value={system}>
                  {system}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Pressure Levels */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <Layers className="w-4 h-4 text-blue-600" />
            Pressure Levels (Multiple Selection)
          </Label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {pressureLevels.map((level) => (
              <div key={level} className="flex items-center space-x-2 p-2 rounded-lg border border-gray-200 hover:bg-blue-50 transition-colors">
                <Checkbox
                  id={`level-${systemNumber}-${level}`}
                  checked={data.levels.includes(level)}
                  onCheckedChange={() => handleLevelToggle(level)}
                />
                <Label
                  htmlFor={`level-${systemNumber}-${level}`}
                  className="text-sm font-medium cursor-pointer flex-1"
                >
                  {level}
                </Label>
              </div>
            ))}
          </div>
          {data.levels.length > 0 && (
            <p className="text-xs text-blue-600 bg-blue-50 p-2 rounded">
              Selected: {data.levels.join(', ')}
            </p>
          )}
        </div>

        {/* Subdivisions - Now with dropdown multi-select */}
        <div className="space-y-3">
          <Label className="text-sm font-medium text-gray-700 flex items-center gap-2">
            <MapPin className="w-4 h-4 text-green-600" />
            Meteorological Subdivisions (Multiple Selection)
          </Label>
          <div className="max-h-48 overflow-y-auto border rounded-lg p-3 bg-gray-50">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {subdivisions.map((subdivision) => (
                <div key={subdivision} className="flex items-center space-x-2 p-1 rounded hover:bg-green-50 transition-colors">
                  <Checkbox
                    id={`subdivision-${systemNumber}-${subdivision}`}
                    checked={data.subdivisions.includes(subdivision)}
                    onCheckedChange={() => handleSubdivisionToggle(subdivision)}
                  />
                  <Label
                    htmlFor={`subdivision-${systemNumber}-${subdivision}`}
                    className="text-xs cursor-pointer flex-1"
                  >
                    {subdivision}
                  </Label>
                </div>
              ))}
            </div>
          </div>
          {data.subdivisions.length > 0 && (
            <p className="text-xs text-green-600 bg-green-50 p-2 rounded">
              Selected ({data.subdivisions.length}): {data.subdivisions.slice(0, 3).join(', ')}
              {data.subdivisions.length > 3 && ` and ${data.subdivisions.length - 3} more...`}
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default WeatherSystemForm;
