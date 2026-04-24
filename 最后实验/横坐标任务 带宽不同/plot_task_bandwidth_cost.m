clc; clear; close all;

scriptDir = fileparts(mfilename('fullpath'));
csvFiles = dir(fullfile(scriptDir, '*.csv'));
assert(~isempty(csvFiles), 'No CSV file found in %s', scriptDir);
filePath = fullfile(scriptDir, csvFiles(1).name);

T = readtable(filePath, 'VariableNamingRule', 'preserve');

x = T.("numTasks");

% Keep only the bandwidth comparison series.
y1 = T.("A(bup=1e7,bdown=5e7)");
y2 = T.("A(bup=2e7,bdown=5e7)");
y3 = T.("A(bup=3e7,bdown=5e7)");
y4 = T.("A(bup=4e7,bdown=5e7)");
y5 = T.("A(bup=5e7,bdown=5e7)");

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
    '1e7', ...
    '2e7', ...
    '3e7', ...
    '4e7', ...
    '5e7'}, ...
    'Location', 'eastoutside', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 12, ...
    'Box', 'on');

grid off;

% print(gcf, fullfile(scriptDir, 'task_bandwidth_comparison_cost.png'), '-dpng', '-r600');
