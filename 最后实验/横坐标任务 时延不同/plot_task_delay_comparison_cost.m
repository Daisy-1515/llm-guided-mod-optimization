clc; clear; close all;

% 在脚本所在目录定位 CSV，避免硬编码绝对路径
scriptDir = fileparts(mfilename('fullpath'));
filePath = fullfile(scriptDir, '横坐标任务-时延对比实验.csv');

% 读取数据，并保留 CSV 中的原始列名
T = readtable(filePath, 'VariableNamingRule', 'preserve');

% 横坐标：任务数
x = T.("numTasks");

% 各方案纵坐标：综合成本
y4 = T.("A(tau=0.5)");
y5 = T.("A(tau=1.0)");
y6 = T.("A(tau=1.5)");
y7 = T.("A(tau=2.0)");

% 可选：最佳可行方案标签
bestPlan = T.("最佳可行方案");

% 创建画布
figure('Color', 'w', 'Position', [200, 120, 920, 650]);
hold on; box on;

% 按参考图风格绘制曲线
plot(x, y4, '-d', ...
    'Color', [0.85 0.33 0.10], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0.85 0.33 0.10]);

plot(x, y5, '-^', ...
    'Color', [0 0.45 0.74], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0 0.45 0.74]);

plot(x, y6, '-v', ...
    'Color', [0.49 0.18 0.56], 'LineWidth', 2.0, ...
    'MarkerSize', 8, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', [0.49 0.18 0.56]);

plot(x, y7, '-p', ...
    'Color', 'm', 'LineWidth', 2.0, ...
    'MarkerSize', 9, 'MarkerFaceColor', 'none', 'MarkerEdgeColor', 'm');

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

yAll = [y4; y5; y6; y7];
ymax = max(yAll);
ylim([0, ceil(ymax / 50) * 50 + 50]);

xlabel('TD 数量', 'FontName', 'SimSun', 'FontSize', 22);
ylabel('综合成本', 'FontName', 'SimSun', 'FontSize', 22);

legend({'A(\tau=0.5)', 'A(\tau=1.0)', 'A(\tau=1.5)', 'A(\tau=2.0)'}, ...
    'Location', 'northwest', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 14, ...
    'NumColumns', 2, ...
    'Box', 'on');

% 保持与参考图接近的简洁风格
grid off;

% 可选：标注“最佳可行方案”
% for i = 1:length(x)
%     text(x(i), y7(i) + 8, bestPlan{i}, ...
%         'FontName', 'Times New Roman', ...
%         'FontSize', 10, ...
%         'HorizontalAlignment', 'center');
% end

% 可选：导出高分辨率图片
% print(gcf, fullfile(scriptDir, 'task_delay_comparison.png'), '-dpng', '-r600');
