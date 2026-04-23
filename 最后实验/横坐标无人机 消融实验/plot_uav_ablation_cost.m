clc; clear; close all;

% 在脚本所在目录定位 CSV，避免硬编码绝对路径
scriptDir = fileparts(mfilename('fullpath'));
filePath = fullfile(scriptDir, '横坐标无人机数量 消融实验.csv');

% 读取数据，并保留 CSV 中的原始列名
T = readtable(filePath, 'VariableNamingRule', 'preserve');

% 横坐标：无人机数量
x = T.("numUAVs");

% 纵坐标：综合成本
y1 = T.("A");
y2 = T.("D1");

% 创建画布
figure('Color', 'w', 'Position', [200, 120, 860, 620]);
hold on; box on;

% 按参考图风格绘制曲线
plot(x, y1, '-o', ...
    'Color', 'm', 'LineWidth', 2.0, ...
    'MarkerSize', 10, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', 'm');

plot(x, y2, '-s', ...
    'Color', [0 0.8 0], 'LineWidth', 2.0, ...
    'MarkerSize', 9, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0 0.8 0]);

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

ymax = max([y1; y2]);
ylim([0, ceil(ymax / 50) * 50 + 50]);

xlabel('无人机数量', 'FontName', 'SimSun', 'FontSize', 22);
ylabel('综合成本', 'FontName', 'SimSun', 'FontSize', 22);

legend({'A', 'D1'}, ...
    'Location', 'northeast', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 16, ...
    'Box', 'on');

% 保持与参考图接近的简洁风格
grid off;

% 可选：导出高分辨率图片
% print(gcf, fullfile(scriptDir, 'uav_ablation_cost.png'), '-dpng', '-r600');
