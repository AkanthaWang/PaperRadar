# 论文总结

## 基本信息
- 标题：The response of flow duration curves to afforestation
- 作者/机构：Patrick N.J. Lane (University of Melbourne), Alice E. Best (CSIRO), Klaus Hickel (CSIRO), Lu Zhang (CSIRO)
- 会议或年份：2005 (Elsevier B.V.)

## 一句话概括
本研究开发了一种基于流量历时曲线（FDC）的模型方法，通过分离降雨和植被年龄的影响，量化了造林对流域流量 regimes 的净影响，并在 10 个流域中验证了该方法与配对流域实验结果的一致性。

## 研究问题
造林对年均流量的水文影响已较清楚，但对流量 regime（由年流量历时曲线 FDC 描述）的影响尚不确定。降雨 variability 会掩盖造林对流量的真实影响，且配对流域（paired catchments）数据并不总是可用。
![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/3e41fa975e4d2f269c98793e0c7e0c3918dd90dbd59fcf53adb8033b1b477d44.jpg)

## 核心方法
研究假设降雨和植被年龄是蒸散发（ET）的主要驱动因素，提出了一种模型来拟合观测到的年 FDC 百分位数时间序列，并通过调整降雨信号来量化造林影响。
1.  **FDC 模型**：使用 Sigmoidal 函数描述造林生长对流量的影响，结合降雨偏差项。
    $$Q _ {\%} = a + b (\Delta P) + \frac {Y}{1 + \exp \left(\frac {T - T _ {\text { half }}}{S}\right)}$$
    其中 $Q_\%$ 为百分位流量，$\Delta P$ 为年降雨偏差，$T$ 为林龄，$T_{\text{half}}$ 为流量减少一半所需时间。
2.  **气候调整**：将 $\Delta P$ 设为 0（长期平均降雨），获得气候调整后的 FDC。
3.  **零流量天数分析**：使用逆 Sigmoidal 函数评估造林对年零流量天数 ($N_{\text{zero}}$) 的影响。
4.  **评估指标**：使用效率系数 (Coefficient of efficiency, E) 评估模型拟合度。
![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/a88bc6901075a10c7d9b6c16913271fc294fb4804c1f794d0423bdcf4f3b148f.jpg)

## 关键实验与结果
研究使用了来自澳大利亚、南非和新西兰的 10 个流域数据（主要为松树造林）。
![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/a7ced540dc14839259d8a77615fb5a4df5d9cb7b414e4977495bb748788ae284.jpg)

-   **模型拟合度**：77% 的拟合返回 $E > 0.7$，60% 达到 0.8 或更好。降雨项在 75% 的分位数中显著，时间项在 80% 的分位数中显著。
    ![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/6a562f2e61d4d6f760224ad8534eec548c641bd78fef1da59b217abb427e1242.jpg)
-   **流量减少模式**：识别出两种响应类型。
    -   **Group 1** (Stewarts Creek, Pine Creek, Redhill)：零流量天数大幅增加，低流量受影响比例高于高流量，导致流量完全停止。
    -   **Group 2** (其他流域)：所有百分位数的流量减少更为均匀。
    ![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/59ebc3a5492a66c21ba85f54d00581522f996476b39c04ad2f2f69729b75a623.jpg)
-   **响应时间**：大多数响应的 $T_{\text{half}}$ 值在 5 到 10 年之间。
    ![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/fc61de34ccbc40bee6070bca4073fdaec9b37ec4cb7e0d9f5d86dab36be99c8c.jpg)
-   **与配对流域对比**：模型估算的总流量和低流量减少量与已发表的配对流域实验结果相当（例如 Cathedral Peak 2 总减少量估算为 57%，文献为 50%）。
    ![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/120a75666732b52eba64d9e2ea07b1c3.jpg)
-   **零流量天数**：在 Group 1 流域，模型 $E$ 值分别为 0.95, 0.99, 0.99，显示造林后零流量天数显著增加（例如 Redhill 从几乎永久流变为高度间歇流）。
    ![](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/b928ca96a523d8daab4cfd345e87b51d3bee3b7ccca0907494cb6d1644d9836c.jpg)

### 相关图表

![Table 10](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/120a75666732b52eba6a432920b2de586af6e8b4b9543d630b64d9e2ea07b1c3.jpg)
*Table 10，page 9，Table 5 Published flow reductions from paired catchment analyses, after Scott et al. (2000), Hickel (2001), Nandakumar and Mein (1993) and Fahey and Jackson (1997) compared to estimated reductions in this study*

## 主要贡献
1.  提供了一种无需配对流域数据即可去除气候（降雨） variability 信号、评估造林对 FDC 净影响的方法。
2.  量化了造林对不同流量百分位数的影响，发现对中位数和低流量的比例影响最大。
3.  识别了两种不同的流域响应组（Group 1 低流量受影响大，Group 2 均匀减少），并指出这与流域存储特性（如土壤深度、BFI）有关。
4.  开发了表征零流量天数变化的方法，可用于评估特定流量发生的可能性变化。

## 局限与不足
-   **模型拟合差异**：Lambrechtsbos A 和 B 的模型拟合度较差（$E$ 值较低，部分低于 0.6），可能因为林分用水在 12 年后 observed annual decrease，不符合模型的 Sigmoidal 渐近假设。
-   **物种数据缺乏**：10 个流域中有 9 个为松树物种，缺乏硬木物种（特别是桉树）在流域尺度的对比数据。
-   **存储参数**：模型未包含存储项（storage term），虽然土壤深度和 BFI 暗示了存储容量的影响，但缺乏准确的存储测量数据。
-   **平衡假设**：模型假设林分用水达到新的平衡，但这在某些物种或林龄下可能不成立（如 20 年后用水可能减少）。

### 相关图表

![Table 5](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/9679ea716634937380d433ae2dbaf1eb155062483ddf46d99a4555ea91cf0aa8.jpg)
*Table 5，page 6，Table 2 Significance of the rainfall and time terms*

![Figure 7](../assets_test3/example_fbac805dc8/bf6b207f-0783-4568-86fa-f8701561a41b/images/bb6391d11a2e83d22b75aac6a30d4432dad58b467ab2504c782dcee930a6fe50.jpg)
*Figure 7，page 7，Fig. 3. Examples of observed and flow duration curves adjusted for average rainfall following afforestation for Stewarts Creek 5, Australia.*

## 可复现信息
-   **模型公式**：文中提供了完整的 FDC 模型 Eq (2) 和零流量天数模型 Eq (3) 及其参数定义。
-   **数据来源**：使用了 10 个具体流域的日流量数据（详见 Table 1），包括澳大利亚、新西兰和南非的流域。
-   **统计方法**：使用了 Coefficient of efficiency (E) 和 t-test 来评估模型显著性。

## 适合引用的结论
-   该模型成功分离了气候和植被对 FDC 的影响，在 10 个流域中的 8 个得到了 adequately described。
-   造林对流量减少的最大比例影响出现在中位数和低流量（10-50th percentiles）。
-   东南澳大利亚的三个小流域（Group 1）显示出最高的流量减少，可能反映了较低的存储容量。
-   该方法可作为配对流域实验的替代方案，用于评估造林对流量历时曲线的净影响。
