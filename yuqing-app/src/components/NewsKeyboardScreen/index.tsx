import React, { useState } from 'react'
import { View, Text } from '@tarojs/components'
import './index.scss'

const TAB_LIST = [
  { key: 'analysis', label: '分析结果' },
  { key: 'news', label: '新闻快讯' },
]

const PERIOD_LIST = ['1D', '1W', '1M', 'YTD', 'All']

const DEFAULT_ARTICLE =
  '【欧盟：愿推动伊朗局势降温 促各方重返谈判桌】当地时间3月9日，欧盟领导人与中东多国领导人就伊朗局势最新进展举行视频会议。欧盟委员会主席冯德莱恩和欧洲理事会主席科斯塔表示，欧盟愿尽可能推动当前伊朗局势降温，促使各方重返谈判桌。根据欧盟方面会后发表的联合声明，欧盟领导人表示，以规则为基础的国际秩序正面临压力，对话和外交是唯一可行的出路。欧盟领导人重申维护地区稳定的承诺，呼吁保护平民，充分尊重国际法和国际人道主义法，并履行遵守《联合国宪章》原则的义务。声明还说，欧盟将根据局势发展调整并加强保护关键水道、防止重要供应链中断的相关行动，以更好应对当前局势带来的挑战。（央视）'

export default function NewsKeyboardScreen() {
  const [activeTab, setActiveTab] = useState('analysis')
  const [activePeriod, setActivePeriod] = useState('YTD')

  return (
    <View className='news-screen'>
      {/* 状态栏占位 + 时间 */}
      <View className='news-screen__status'>
        <Text className='news-screen__time'>9:30</Text>
      </View>

      {/* 搜索框：我关注 */}
      <View className='news-screen__search-wrap'>
        <View className='news-screen__search'>
          <Text className='news-screen__search-placeholder'>我关注</Text>
        </View>
      </View>

      {/* 标题卡片：国际石油价格飙升 */}
      <View className='news-screen__card'>
        <Text className='news-screen__card-title'>国际石油价格飙升</Text>
        <View className='news-screen__card-arrow' />
      </View>

      {/* Tab：分析结果 / 新闻快讯 */}
      <View className='news-screen__tabs'>
        {TAB_LIST.map((tab) => (
          <View
            key={tab.key}
            className={`news-screen__tab ${activeTab === tab.key ? 'news-screen__tab--active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            <Text className='news-screen__tab-text'>{tab.label}</Text>
            {activeTab === tab.key && <View className='news-screen__tab-line' />}
          </View>
        ))}
        <View className='news-screen__tab' />
      </View>

      <View className='news-screen__divider' />

      {/* 正文 + 图表区 */}
      <View className='news-screen__content'>
        <Text className='news-screen__article'>{DEFAULT_ARTICLE}</Text>

        <View className='news-screen__chart-wrap'>
          <View className='news-screen__chart-placeholder' />
          <View className='news-screen__periods'>
            {PERIOD_LIST.map((p) => (
              <View
                key={p}
                className={`news-screen__period ${activePeriod === p ? 'news-screen__period--active' : ''}`}
                onClick={() => setActivePeriod(p)}
              >
                <Text className='news-screen__period-text'>{p}</Text>
              </View>
            ))}
          </View>
        </View>
      </View>

      {/* 底部 Home 指示条 */}
      <View className='news-screen__home-bar'>
        <View className='news-screen__home-indicator' />
      </View>
    </View>
  )
}
