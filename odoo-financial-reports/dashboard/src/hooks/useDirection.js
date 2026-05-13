import { useLanguage } from '../context/LanguageContext';

export const useDirection = () => {
  const { isRTL } = useLanguage();
  return isRTL ? 'rtl' : 'ltr';
};
