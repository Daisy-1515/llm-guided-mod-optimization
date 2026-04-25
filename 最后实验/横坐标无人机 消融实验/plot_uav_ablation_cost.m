clc; clear; close all;

% 自动定位当前目录下唯一的 CSV，避免硬编码中文路径。
scriptDir = fileparts(mfilename('fullpath'));
csvFiles = dir(fullfile(scriptDir, '*.csv'));
assert(~isempty(csvFiles), 'No CSV file found in the script directory.');
filePath = fullfile(scriptDir, csvFiles(1).name);

% 保留原始列名，但按列索引读取以规避编码问题。
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

xlabel(char([26080 20154 26426 25968 37327]), 'FontName', 'SimSun', 'FontSize', 22);
ylabel(char([32508 21512 25104 26412]), 'FontName', 'SimSun', 'FontSize', 22);

legend({char([20840 26412 22320]), 'D1', char([32431 76 76 77]), 'LLM+HS'}, ...
    'Location', 'northeast', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 16, ...
    'Box', 'on');

grid off;

% 可选：导出高清图片。
% print(gcf, fullfile(scriptDir, 'uav_count_ablation_cost.png'), '-dpng', '-r600');
