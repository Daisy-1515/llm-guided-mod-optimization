clc; clear; close all;

% Compare LLM+HS under different bandwidth settings.
scriptDir = fileparts(mfilename('fullpath'));
csvFiles = dir(fullfile(scriptDir, '*.csv'));
assert(~isempty(csvFiles), 'No CSV file found in %s', scriptDir);
filePath = fullfile(scriptDir, csvFiles(1).name);

T = readtable(filePath, 'VariableNamingRule', 'preserve');

x = T{:, 1};
y1 = T{:, 5};
y2 = T{:, 6};
y3 = T{:, 7};
y4 = T{:, 8};
y5 = T{:, 9};

figure('Color', 'w', 'Position', [180, 100, 980, 680]);
hold on; box on;

plot(x, y1, '-d', ...
    'Color', [0.00 0.45 0.74], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y2, '-p', ...
    'Color', [0.49 0.18 0.56], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y3, '-h', ...
    'Color', [0.93 0.69 0.13], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y4, '-<', ...
    'Color', [0.30 0.75 0.93], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y5, '->', ...
    'Color', [0.64 0.08 0.18], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

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

allY = [y1; y2; y3; y4; y5];
allY = allY(~isnan(allY));
ylim([0, ceil(max(allY) / 50) * 50 + 50]);

xlabel(char([84 68 32 25968 37327]), 'FontName', 'SimSun', 'FontSize', 22);
ylabel(char([32508 21512 25104 26412]), 'FontName', 'SimSun', 'FontSize', 22);

legend({ ...
    'LLM+HS (1 Mbps)', ...
    'LLM+HS (2 Mbps)', ...
    'LLM+HS (3 Mbps)', ...
    'LLM+HS (4 Mbps)', ...
    'LLM+HS (5 Mbps)'}, ...
    'Location', 'eastoutside', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 12, ...
    'Box', 'on');

grid off;

% print(gcf, fullfile(scriptDir, 'task_bandwidth_comparison_cost.png'), '-dpng', '-r600');
