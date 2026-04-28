clc; clear; close all;

% Rebuild the task-count ablation figure using the finalized algorithm labels.
scriptDir = fileparts(mfilename('fullpath'));
fileName = char([27178 22352 26631 20219 21153 25968 32 28040 34701 23454 39564 46 99 115 118]);
filePath = fullfile(scriptDir, fileName);
assert(isfile(filePath), 'Expected CSV file is missing: %s', filePath);

T = readtable(filePath, 'VariableNamingRule', 'preserve');

x = T{:, 1};
y1 = T{:, 2};
y2 = T{:, 3};
y3 = T{:, 4};
y4 = T{:, 5};

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

xlabel(char([84 68 32 25968 37327]), 'FontName', 'SimSun', 'FontSize', 22);
ylabel(char([32508 21512 25104 26412]), 'FontName', 'SimSun', 'FontSize', 22);

legend({'ALA', 'Default Objective', 'LOGO', 'LLM+HS'}, ...
    'Location', 'southeast', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 16, ...
    'Box', 'on');

grid off;

% Optional export for publication-quality figures.
% print(gcf, fullfile(scriptDir, 'task_count_ablation_cost.png'), '-dpng', '-r600');
