import { Ionicons } from "@expo/vector-icons";
import { createBottomTabNavigator } from "@react-navigation/bottom-tabs";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import type { ComponentProps } from "react";
import { ActivityIndicator, View } from "react-native";
import { useAuth } from "../auth";
import { colors } from "../theme";

import LoginScreen from "../screens/auth/LoginScreen";
import SignupScreen from "../screens/auth/SignupScreen";
import AlertsScreen from "../screens/donor/AlertsScreen";
import DonateDetailsScreen from "../screens/donor/DonateDetailsScreen";
import DonationDetailScreen from "../screens/donor/DonationDetailScreen";
import DonateScreen from "../screens/donor/DonateScreen";
import DonationsScreen from "../screens/donor/DonationsScreen";
import HomeScreen from "../screens/donor/HomeScreen";
import NeedsScreen from "../screens/donor/NeedsScreen";
import TrackingScreen from "../screens/donor/TrackingScreen";
import ProfileScreen from "../screens/ProfileScreen";
import ActiveJobScreen from "../screens/rider/ActiveJobScreen";
import HistoryScreen from "../screens/rider/HistoryScreen";
import JobsScreen from "../screens/rider/JobsScreen";
import PendingScreen from "../screens/rider/PendingScreen";
import ProofScreen from "../screens/rider/ProofScreen";

const Stack = createNativeStackNavigator();
const Tab = createBottomTabNavigator();

type IconName = ComponentProps<typeof Ionicons>["name"];

const tabOptions = (icon: IconName, label: string) => ({
  title: label,
  tabBarIcon: ({ color, size }: { color: string; size: number }) => <Ionicons name={icon} color={color} size={size} />,
});

function DonorTabs() {
  return (
    <Tab.Navigator screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted }}>
      <Tab.Screen name="Home" component={HomeScreen} options={tabOptions("home-outline", "Home")} />
      <Tab.Screen name="Donate" component={DonateScreen} options={tabOptions("add-circle-outline", "Donate")} />
      <Tab.Screen name="Donations" component={DonationsScreen} options={tabOptions("cube-outline", "Donations")} />
      <Tab.Screen name="Alerts" component={AlertsScreen} options={tabOptions("notifications-outline", "Alerts")} />
      <Tab.Screen name="Profile" component={ProfileScreen} options={tabOptions("person-outline", "Profile")} />
    </Tab.Navigator>
  );
}

function RiderTabs() {
  return (
    <Tab.Navigator screenOptions={{ headerShown: false, tabBarActiveTintColor: colors.primary, tabBarInactiveTintColor: colors.muted }}>
      <Tab.Screen name="Jobs" component={JobsScreen} options={tabOptions("list-outline", "Jobs")} />
      <Tab.Screen name="ActiveJob" component={ActiveJobScreen} options={tabOptions("bicycle-outline", "Active job")} />
      <Tab.Screen name="History" component={HistoryScreen} options={tabOptions("time-outline", "History")} />
      <Tab.Screen name="RiderProfile" component={ProfileScreen} options={tabOptions("person-outline", "Profile")} />
    </Tab.Navigator>
  );
}

/** Shows the right app for who is logged in: auth screens, donor app or rider app. */
export default function RootNavigator() {
  const { status, user } = useAuth();

  if (status === "loading") {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }

  if (!user) {
    return (
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Login" component={LoginScreen} />
        <Stack.Screen name="Signup" component={SignupScreen} options={{ headerShown: true, title: "Create account" }} />
      </Stack.Navigator>
    );
  }

  // Riders see the documents / review screen until an admin approves them
  if (user.role === "rider" && user.rider_status !== "approved") {
    return (
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Pending" component={PendingScreen} />
      </Stack.Navigator>
    );
  }

  if (user.role === "rider") {
    return (
      <Stack.Navigator>
        <Stack.Screen name="RiderTabs" component={RiderTabs} options={{ headerShown: false }} />
        <Stack.Screen name="Proof" component={ProofScreen} options={{ title: "Proof" }} />
      </Stack.Navigator>
    );
  }

  return (
    <Stack.Navigator>
      <Stack.Screen name="DonorTabs" component={DonorTabs} options={{ headerShown: false }} />
      <Stack.Screen name="DonateDetails" component={DonateDetailsScreen} options={{ title: "New donation" }} />
      <Stack.Screen name="DonationDetail" component={DonationDetailScreen} options={{ title: "Donation" }} />
      <Stack.Screen name="Tracking" component={TrackingScreen} options={{ title: "Live tracking" }} />
      <Stack.Screen name="Needs" component={NeedsScreen} options={{ title: "What is needed where" }} />
    </Stack.Navigator>
  );
}
