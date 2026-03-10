import { useState, useEffect } from 'react'
import { View, Text, ScrollView } from '@tarojs/components'
import { AtTabs, AtTabsPane, AtList, AtListItem, AtTag, AtProgress, AtIcon } from 'taro-ui'
import Taro from '@tarojs/taro'
import NavHeader from '../../components/NavHeader'
import './index.scss'

const TAB_LIST = [
  { title: '新闻汇总' },
  { title: '思考过程' },
  { title: '分析结果' },
]

const SUB_TAB_LIST = ['步骤一', '步骤二', '步骤三']

const MOCK_NEWS = [
  { id: 1, title: '相关快讯标题一', source: '来源A', time: '10:30' },
  { id: 2, title: '相关快讯标题二', source: '来源B', time: '10:25' },
  { id: 3, title: '相关快讯标题三', source: '来源C', time: '10:20' },
]

export default function Result() {
  const [keyword, setKeyword] = useState('')
  const [currentTab, setCurrentTab] = useState(0)
  const [subTab, setSubTab] = useState(0)
  const [streamText, setStreamText] = useState('')
  const [streaming, setStreaming] = useState(false)

  useEffect(() => {
    const router = Taro.getCurrentInstance().router
    const k = router?.params?.keyword || ''
    setKeyword(decodeURIComponent(k || ''))
  }, [])

  useEffect(() => {
    if (currentTab === 1 && subTab >= 0) {
      setStreaming(true)
      setStreamText('')
      const content = ['正在检索相关资讯…', '正在分析舆情倾向…', '正在生成结论…'][subTab] || '处理中…'
      let i = 0
      const timer = setInterval(() => {
        if (i < content.length) {
          setStreamText((prev) => prev + content[i])
          i++
        } else {
          clearInterval(timer)
          setStreaming(false)
        }
      }, 80)
      return () => clearInterval(timer)
    }
  }, [currentTab, subTab])

  return (
    <View className='page-result'>
      <NavHeader title={keyword || '分析结果'} showBack />
      <View className='page-result__tabs'>
        <AtTabs current={currentTab} tabList={TAB_LIST} onClick={(i) => setCurrentTab(i)}>
          <AtTabsPane current={currentTab} index={0}>
            <ScrollView scrollY className='pane-scroll'>
              <View className='pane-section'>
                <Text className='pane-title'>新闻快讯列表</Text>
                <AtList>
                  {MOCK_NEWS.map((n) => (
                    <AtListItem key={n.id} title={n.title} note={`${n.source} · ${n.time}`} arrow='right' />
                  ))}
                </AtList>
              </View>
              <View className='pane-section'>
                <Text className='pane-title'>分析结论</Text>
                <View className='pane-card'>
                  <Text className='pane-text'>
                    基于当前关键词「{keyword}」的舆情汇总：相关报道共 3 条，整体情绪偏中性，建议关注后续政策与市场动态。
                  </Text>
                </View>
              </View>
            </ScrollView>
          </AtTabsPane>
          <AtTabsPane current={currentTab} index={1}>
            <View className='pane-subtabs'>
              {SUB_TAB_LIST.map((t, i) => (
                <View
                  key={i}
                  className={'pane-subtab' + (subTab === i ? ' pane-subtab--active' : '')}
                  onClick={() => setSubTab(i)}
                >
                  {t}
                </View>
              ))}
            </View>
            <ScrollView scrollY className='pane-scroll pane-stream'>
              <View className='pane-card'>
                {streaming && <AtIcon value='loading' size='20' className='stream-icon' />}
                <Text className='pane-text stream-text'>{streamText || '选择上方步骤查看思考过程'}</Text>
              </View>
            </ScrollView>
          </AtTabsPane>
          <AtTabsPane current={currentTab} index={2}>
            <ScrollView scrollY className='pane-scroll'>
              <View className='pane-section'>
                <Text className='pane-title'>文字汇总</Text>
                <View className='pane-card'>
                  <Text className='pane-text'>
                    舆情分析结果：话题热度中等，正面与中性占比较高，主要讨论集中在行业影响与政策预期，建议持续跟踪核心信源。
                  </Text>
                </View>
              </View>
              <View className='pane-section'>
                <Text className='pane-title'>数据概览</Text>
                <View className='pane-charts'>
                  <View className='chart-item'>
                    <Text className='chart-label'>情感分布</Text>
                    <AtProgress percent={60} status='progress' strokeWidth={12} />
                    <Text className='chart-note'>正面+中性 约 60%</Text>
                  </View>
                  <View className='chart-item'>
                    <Text className='chart-label'>热度指数</Text>
                    <AtProgress percent={45} status='progress' strokeWidth={12} />
                    <Text className='chart-note'>当前 45</Text>
                  </View>
                </View>
              </View>
            </ScrollView>
          </AtTabsPane>
        </AtTabs>
      </View>
    </View>
  )
}
