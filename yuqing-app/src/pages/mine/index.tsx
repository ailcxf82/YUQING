import { View, Text, ScrollView } from '@tarojs/components'
import { AtList, AtListItem, AtAvatar } from 'taro-ui'
import Taro from '@tarojs/taro'
import NavHeader from '../../components/NavHeader'
import './index.scss'

export default function Mine() {
  const onNav = (url: string) => () => Taro.navigateTo({ url })
  const onSettings = () => {
    Taro.showToast({ title: '设置功能开发中', icon: 'none' })
  }

  return (
    <View className='page-mine'>
      <NavHeader title='我的' showSettings onSettingsClick={onSettings} />
      <ScrollView scrollY className='page-mine__body'>
        <View className='page-mine__user'>
          <AtAvatar image='' text='用' size='large' circle />
          <Text className='page-mine__name'>用户</Text>
          <Text className='page-mine__desc'>舆情分析助手</Text>
        </View>
        <View className='page-mine__menu'>
          <AtList>
            <AtListItem title='搜索历史' arrow='right' onClick={onNav('/pages/index/index')} />
            <AtListItem title='收藏与订阅' arrow='right' onClick={() => Taro.showToast({ title: '敬请期待', icon: 'none' })} />
            <AtListItem title='消息通知' arrow='right' onClick={() => Taro.showToast({ title: '敬请期待', icon: 'none' })} />
            <AtListItem title='设置' arrow='right' onClick={onSettings} />
          </AtList>
        </View>
      </ScrollView>
    </View>
  )
}
