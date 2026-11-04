# 多参考环B：C99匹配核心

本模块只接收已归一化的12×360 S8 profile，保留原27个中心/尺度假设、两份训练模板、49个整数旋转候选及原门槛。图像前端、同源ROI生命周期、CNN、标定及显示不属于本C文件；未链接整版MCU应用、未上板。

接口见 `meter_pose_matcher.h`：

1. `mp_template_init`借用训练模板index/value及Python预先导出的49项local_shift，不自行重新计算round。
2. `mp_prepare(ctx, center_allowed)`接收同一预测hub是否满足距中心≤14的前端结果，不是外界放行信号。
3. 按原dx→dy→scale循环顺序调用 `mp_push`；outside_count>216/4320的profile跳过。
4. `mp_finish`返回旋转、赢家来源、trim分子/分母及score/margin/interior三门。

256项U16误差直方图逐项取最小floor(0.8N)项，包含截断bin，等价原np.partition最低80% SAD。跨模板以有理数交叉乘比较均值，精确同分保最先profile/template；旋转同分保最小索引。margin比较范围为离最优旋转严格超过5°的候选。score≥0.64、margin≥0.018、abs(delta)<24保持原样。

`host_tests.py`仅用合成数据：833个逐shift trim/赢家核对、14个冻结模板score边界、3096个margin边界通过。原D模板1634点keep1307、E模板1600点keep1280已由主负责人另外用223组真实既有fixture逐项核对通过，真实fixture回执由主负责人维护。

范围限制：通用keep=125可以使数学恰好0.018的边界遇到原float64相减舍入差，例如best_sum2/far_sum290。当前冻结keep1280/1307的边界核对通过，不承诺任意新模板也与原IEEE消减逐位等价，不可静默换mask后沿用兼容结论。C核心采用准确有理数门，未针对G移动门槛。

`rv32_build/rv32_object_receipt.json`绑定SDK真实RV32IMAC C99 object：text1548B，rodata/data/BSS0，mp_push本地静态栈96B，未解析仅memset，无libgcc或浮点helper。BSS0源于caller提供context及profile，不是零工作内存；context1104B、单profile4320B、冻结模板values3234B＋indices6468B＋shift196B均须纳入整体生命周期。静态栈不是实测watermark，代码大小不是整应用已fit。

`inspect_rv32_object.py`可重新读取已生成object的section、symbol和stack信息；不会执行应用链接或设备操作。host测试会重新编译此目录的独立DLL，不改旧工程，运行中DLL被占用时请勿同时重编。
