clc; clear; close all;

% 在脚本所在目录定位 CSV，便于直接复现实验图
scriptDir = fileparts(mfilename('fullpath'));
filePath = fullfile(scriptDir, '横坐标任务-带宽对比实验.csv');

% 读取数据，并保留原始列名
T = readtable(filePath, 'VariableNamingRule', 'preserve');

% 横坐标：任务数量
x = T.("numTasks");

% 纵坐标：各方案综合成本
y1 = T.("all-local");
y2 = T.("D1");
y3 = T.("pure LLM(B)");
y4 = T.("A(bup=1e7,bdown=5e7)");
y5 = T.("A(bup=2e7,bdown=5e7)");
y6 = T.("A(bup=3e7,bdown=5e7)");
y7 = T.("A(bup=4e7,bdown=5e7)");
y8 = T.("A(bup=5e7,bdown=5e7)");

% 创建画布
figure('Color', 'w', 'Position', [180, 100, 980, 680]);
hold on; box on;

% 按参考图风格绘制不同带宽方案曲线
plot(x, y1, '-o', ...
    'Color', [0.85 0.10 0.10], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y2, '-s', ...
    'Color', [0.00 0.60 0.00], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y3, '-^', ...
    'Color', [0.00 0.00 0.00], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y4, '-d', ...
    'Color', [0.00 0.45 0.74], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y5, '-p', ...
    'Color', [0.49 0.18 0.56], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y6, '-h', ...
    'Color', [0.93 0.69 0.13], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y7, '-<', ...
    'Color', [0.30 0.75 0.93], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

plot(x, y8, '->', ...
    'Color', [0.64 0.08 0.18], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none');

% 坐标轴样式
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

allY = [y1; y2; y3; y4; y5; y6; y7; y8];
allY = allY(~isnan(allY));
ylim([0, ceil(max(allY) / 50) * 50 + 50]);

xlabel('TD 数量', 'FontName', 'SimSun', 'FontSize', 22);
ylabel('综合成本', 'FontName', 'SimSun', 'FontSize', 22);

legend({ ...
    'all-local', ...
    'D1', ...
    'pure LLM(B)', ...
    'A(bup=1e7,bdown=5e7)', ...
    'A(bup=2e7,bdown=5e7)', ...
    'A(bup=3e7,bdown=5e7)', ...
    'A(bup=4e7,bdown=5e7)', ...
    'A(bup=5e7,bdown=5e7)'}, ...
    'Location', 'eastoutside', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 12, ...
    'Box', 'on');

% 保持与参考图接近的简洁风格
grid off;

% 可选：导出高清图片
% print(gcf, fullfile(scriptDir, 'task_bandwidth_comparison_cost.png'), '-dpng', '-r600');
