clc; clear; close all;

% Resolve the only CSV in this directory to avoid hard-coded Unicode paths.
scriptDir = fileparts(mfilename('fullpath'));
csvFiles = dir(fullfile(scriptDir, '*.csv'));
assert(~isempty(csvFiles), 'No CSV file found in the script directory.');
filePath = fullfile(scriptDir, csvFiles(1).name);

% Preserve source column names, but read by column index for encoding safety.
T = readtable(filePath, 'VariableNamingRule', 'preserve');

x = T{:, 1};
y1 = T{:, 2};
y2 = T{:, 4};
y3 = T{:, 6};
y4 = T{:, 8};

figure('Color', 'w', 'Position', [200, 120, 860, 620]);
hold on; box on;

plot(x, y1, '-o', ...
    'Color', 'r', 'LineWidth', 2.0, ...
    'MarkerSize', 10, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', 'r');

plot(x, y2, '-s', ...
    'Color', [0 0.8 0], 'LineWidth', 2.0, ...
    'MarkerSize', 9, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0 0.8 0]);

plot(x, y3, '-*', ...
    'Color', 'k', 'LineWidth', 2.0, ...
    'MarkerSize', 11);

plot(x, y4, '-d', ...
    'Color', 'm', 'LineWidth', 2.0, ...
    'MarkerSize', 10, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', 'm');

ax = gca;
ax.FontName = 'Times New Roman';
ax.FontSize = 18;
ax.LineWidth = 1.0;
ax.TickDir = 'in';
ax.Box = 'on';
ax.XMinorTick = 'off';
ax.YMinorTick = 'off';

xticks(x);
xlim([min(x), max(x)]);

ymax = max([y1; y2; y3; y4]);
ylim([0, ceil(ymax / 50) * 50 + 50]);

xlabel('Number of UAVs', 'FontName', 'Times New Roman', 'FontSize', 22);
ylabel('Total Cost', 'FontName', 'Times New Roman', 'FontSize', 22);

legend({'All Local', 'D1', 'LLM', 'LLM+HS'}, ...
    'Location', 'northeast', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 16, ...
    'Box', 'on');

grid off;

% Optional high-resolution export.
% print(gcf, fullfile(scriptDir, 'uav_count_ablation_cost.png'), '-dpng', '-r600');
