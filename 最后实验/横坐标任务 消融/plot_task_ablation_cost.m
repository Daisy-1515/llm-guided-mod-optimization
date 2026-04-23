clc; clear; close all;

% 在脚本所在目录定位 CSV，便于在项目中直接复现实验图，
% 避免使用硬编码的绝对路径。
scriptDir = fileparts(mfilename('fullpath'));
filePath = fullfile(scriptDir, '横坐标任务数 消融实验.csv');

% 读取数据，并保留 CSV 中的原始列名。
T = readtable(filePath, 'VariableNamingRule', 'preserve');

% 横坐标：任务数
x = T.("numTasks");

% 纵坐标：仅使用综合成本
y1 = T.("本地执行");
y2 = T.("标准目标函数");
y3 = T.("LLM");
y4 = T.("LLM+HS");

% 创建画布
figure('Color', 'w', 'Position', [200, 120, 860, 620]);
hold on; box on;

% 按照参考图风格绘制曲线
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

ymax = max([y1; y2; y3; y4]);
ylim([0, ceil(ymax / 50) * 50 + 50]);

xlabel('TD 数量', 'FontName', 'SimSun', 'FontSize', 22);
ylabel('综合成本', 'FontName', 'SimSun', 'FontSize', 22);

% 图例
legend({'本地执行', '标准目标函数', 'LLM', 'LLM+HS'}, ...
    'Location', 'southeast', ...
    'FontName', 'Times New Roman', ...
    'FontSize', 16, ...
    'Box', 'on');

% legend({'all-local', 'D1', 'pure LLM(B)', 'A(bup=1e7,bdown=5e7)'}, ...
%     'Location', 'northwest', ...
%     'FontName', 'Times New Roman', ...
%     'FontSize', 16, ...
%     'Box', 'on');






% 保持与参考图接近的简洁风格
grid off;

% 可选：导出高分辨率图片
% print(gcf, fullfile(scriptDir, 'task_count_ablation_cost.png'), '-dpng', '-r600');
