import { View, Text } from '@tarojs/components'
import { AtIcon } from 'taro-ui'
import Taro from '@tarojs/taro'
import './index.scss'

interface NavHeaderProps {
  title: string
  showBack?: boolean
  showSettings?: boolean
  onSettingsClick?: () => void
}

export default function NavHeader({ title, showBack = false, showSettings = false, onSettingsClick }: NavHeaderProps) {
  const menuButtonInfo = Taro.getEnv() === Taro.ENV_TYPE.WEAPP
    ? Taro.getMenuButtonBoundingClientRect()
    : null
  const statusBarHeight = menuButtonInfo ? menuButtonInfo.top : 44
  const navHeight = menuButtonInfo ? menuButtonInfo.height + 8 : 44

  const handleBack = () => {
    Taro.navigateBack({ delta: 1 })
  }

  return (
    <View className='nav-header' style={{ paddingTop: `${statusBarHeight}px` }}>
      <View className='nav-header__content' style={{ height: `${navHeight}px` }}>
        <View className='nav-header__left'>
          {showBack && (
            <View className='nav-header__back' onClick={handleBack}>
              <AtIcon value='chevron-left' size='24' color='#333' />
            </View>
          )}
          {showSettings && (
            <View className='nav-header__settings' onClick={onSettingsClick}>
              <AtIcon value='settings' size='20' color='#333' />
            </View>
          )}
        </View>
        <View className='nav-header__title'>
          <Text>{title}</Text>
        </View>
        <View className='nav-header__right' />
      </View>
    </View>
  )
}
