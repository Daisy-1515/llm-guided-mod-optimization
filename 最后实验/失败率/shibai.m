clc; clear; close all;

% Task-state comparison between the proposed method and the default-objective baseline.
groups = {'LLM+HS', 'Default Objective'};
localProcess = [13, 81];
uavOffload = [797, 694];
failedTasks = [61, 96];

x = 1:2;
w = 0.22;

figure('Color', 'w', 'Position', [300 200 620 420]);
hold on;

b1 = bar(x - w, localProcess, w, 'FaceColor', [0.93 0.69 0.13], 'EdgeColor', 'k');
b2 = bar(x,     uavOffload,   w, 'FaceColor', [0.00 0.45 0.74], 'EdgeColor', 'k');
b3 = bar(x + w, failedTasks,  w, 'FaceColor', [0.85 0.33 0.10], 'EdgeColor', 'k');

ax = gca;
ax.XTick = x;
ax.XTickLabel = groups;
ax.FontName = 'Times New Roman';
ax.FontSize = 12;
ax.LineWidth = 1.0;
ax.Box = 'on';

ylabel(char([20219 21153 25968 37327]), 'FontName', 'SimSun', 'FontSize', 13);
ylim([0 850]);

legend([b1, b2, b3], ...
    {char([26412 22320 22788 29702]), char([85 65 86 21368 36733]), char([22833 36133])}, ...
    'Location', 'north', ...
    'FontName', 'SimSun', ...
    'FontSize', 11, ...
    'Box', 'on');

hold off;
