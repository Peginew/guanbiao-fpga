# Q5坐标输入的C99像素与径向profile前端

范围仅三项整数数学：9×9局部均值/对比度、Q5双线性取样、12×360径向profile有理数归一化。源码为 `meter_pose_frontend.c/.h`；Python公式固定于 `pose_frontend.py` SHA4f6d09ad…8120。未改matcher、网络、既有工程、阈值或设备。

- 均值：replicate边界，mean=(81点和+40)/81，随后satU8(3×(pixel−mean)+128)。9行U8＋128列U16和为1408B，支持完全同址输入输出。
- Q5取样：signed坐标负数按floor除32；四邻越界填128；合并双线性权重后(sum+512)>>10。坐标表由调用者提供，C中不运行sin/cos、hub/radius变换或几何量化。
- Profile：d=360u−行和；A=Σabs(d)；RNE-even(d×11520/max(A,777600))后饱和[-127,127]，所有数学中间值可用S32。融合接口仅临时存一行360B，不建4320B的额外sample矩阵。

**outside_count必须保留原float64几何在Q5量化前的判定。** 不能从Q5反推并替换旧门。表坐标、边界判定及hub距离仍由调用者生成，所以本模块不等于完整整数几何。

`host_frontend_test_receipt.json`记录合成验证：均值262144像素和同址262144像素、Q5负坐标/边界/CV2对照77312像素、profile及同址各138240元素、融合69120元素，正负RNE半整数与双端饱和通过。没有使用真实数据或训练。整数profile按精确有理数RNE定义，与旧float32在极少数舍入tie上可能差1；真实同ROI逐项与最终许可对照由主负责人维护，不将前端数学通过当作读数提升。

SDK实际RV32IMAC C99 object见 `rv32_build/rv32_frontend_object_receipt.json`：text1320B，rodata/data/BSS0，无未解析/浮点/libgcc调用；最大本地栈32B，已知融合调用链48B，不包括应用及中断。完整Q5 x/y表17280B、normalized图16384B、输出profile4320B和调用者workspace均必须另外核算；BSS0不代表这些数据免费或已可装入当前48KiB TCM。

范围到此结束：没有生成全整数几何、移植整网、执行整版MCU链接或板测。复核合成数学可运行 `host_frontend_tests.py`，只读取现有新DLL；读取object成本可运行 `inspect_frontend_object.py`，不进行应用编译或设备操作。
