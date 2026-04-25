clc; clear; close all;

% 近似数据（按图片估计）
groups = {'本文提出的LLM辅助优化算法', '未优化'};
local_process = [15, 95];      % 本地处理
ris_offload   = [820, 695];    % LLM辅助卸载
failed        = [165, 210];    % 失败

% 组位置
x = 1:2;
w = 0.22;

figure('Color', 'w', 'Position', [300 200 560 380]);
hold on;

% 三组柱
b1 = bar(x - w, local_process, w, 'FaceColor', [0.93 0.69 0.13], 'EdgeColor', 'k');
b2 = bar(x,      ris_offload,   w, 'FaceColor', [0.00 0.45 0.74], 'EdgeColor', 'k');
b3 = bar(x + w,  failed,        w, 'FaceColor', [0.85 0.33 0.10], 'EdgeColor', 'k');

% 坐标轴与标签
set(gca, ...
    'XTick', x, ...
    'XTickLabel', groups, ...
    'FontSize', 12, ...
    'LineWidth', 1.0, ...
    'Box', 'on');

ylabel('任务数量', 'FontSize', 13);
ylim([0 850]);

% 图例
legend([b1, b2, b3], {'本地处理', 'LLM辅助卸载', '失败'}, ...
    'Location', 'north', ...
    'FontSize', 11, ...
    'Box', 'on');

% 中文显示更稳一些
set(gca, 'FontName', 'SimHei');
set(get(gca, 'YLabel'), 'FontName', 'SimHei');
set(legend, 'FontName', 'SimHei');

hold off;
