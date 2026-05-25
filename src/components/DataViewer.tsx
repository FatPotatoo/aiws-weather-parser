import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';

export interface WeatherEntry {
  id: string;
  date: string;
  system: string;
  pressure_levels: string[];
  subdivisions: string[];
}

interface DataViewerProps {
  entries: WeatherEntry[];
  onBack: () => void;
  onDelete: (id: string) => void;
}

type GroupedData = {
  [system: string]: {
    [level: string]: Set<string>;
  };
};

const DataViewer: React.FC<DataViewerProps> = ({ entries, onBack, onDelete }) => {
  const [searchDate, setSearchDate] = useState('');
  const [searchSubdivision, setSearchSubdivision] = useState('');

  const filteredEntries = entries.filter(entry =>
    (searchDate === '' || entry.date === searchDate) &&
    (searchSubdivision === '' || entry.subdivisions.some(sub =>
      sub.toLowerCase().includes(searchSubdivision.toLowerCase())))
  );

  const grouped: GroupedData = filteredEntries.reduce((acc, entry) => {
    if (!acc[entry.system]) acc[entry.system] = {};
    entry.pressure_levels.forEach(level => {
      if (!acc[entry.system][level]) acc[entry.system][level] = new Set();
      entry.subdivisions.forEach(sub => {
        acc[entry.system][level].add(sub);
      });
    });
    return acc;
  }, {} as GroupedData);

  return (
    <div className="p-4 space-y-4">
      <div className="flex gap-4 mb-4">
        <Input
          type="date"
          value={searchDate}
          onChange={(e) => setSearchDate(e.target.value)}
          className="max-w-xs"
        />
        <Input
          placeholder="Filter by Subdivision"
          value={searchSubdivision}
          onChange={(e) => setSearchSubdivision(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {Object.keys(grouped).length === 0 ? (
        <div className="text-gray-500 text-center">No entries found.</div>
      ) : (
        Object.entries(grouped).map(([system, levels]) => (
          <Card key={system} className="bg-gray-100">
            <CardHeader>
              <CardTitle className="text-lg">{system}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {Object.entries(levels).map(([level, subs]) => (
                <div key={level}>
                  <h4 className="font-semibold text-gray-700">Pressure Level: {level}</h4>
                  <div className="flex flex-wrap gap-2">
                    {Array.from(subs).map(sub => (
                      <Badge key={sub} className="bg-blue-100 text-blue-900">{sub}</Badge>
                    ))}
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
};

export default DataViewer;

