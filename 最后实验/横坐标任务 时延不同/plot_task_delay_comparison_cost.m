clc; clear; close all;

% Compare LLM+HS under different delay thresholds.
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

figure('Color', 'w', 'Position', [200, 120, 920, 650]);
hold on; box on;

plot(x, y1, '-d', ...
    'Color', [0.85 0.33 0.10], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0.85 0.33 0.10]);

plot(x, y2, '-^', ...
    'Color', [0 0.45 0.74], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0 0.45 0.74]);

plot(x, y3, '-v', ...
    'Color', [0.49 0.18 0.56], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0.49 0.18 0.56]);

plot(x, y4, '-p', ...
    'Color', 'm', 'LineWidth', 2.0, ...
    'MarkerSize', 9, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', 'm');

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

yAll = [y1; y2; y3; y4];
yAll = yAll(~isnan(yAll));
ylim([0, ceil(max(yAll) / 50) * 50 + 50]);

xlabel(char([84 68 32 25968 37327]), 'FontName', 'SimSun', 'FontSize', 22);
ylabel(char([32508 21512 25104 26412]), 'FontName', 'SimSun', 'FontSize', 22);

legend({'LLM+HS (\tau=0.5)', 'LLM+HS (\tau=1.0)', 'LLM+HS (\tau=1.5)', 'LLM+HS (\tau=2.0)'}, ...
    'Location', 'northwest', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 14, ...
    'NumColumns', 2, ...
    'Box', 'on');

grid off;

% print(gcf, fullfile(scriptDir, 'task_delay_comparison.png'), '-dpng', '-r600');
