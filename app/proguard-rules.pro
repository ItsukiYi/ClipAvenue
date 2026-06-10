# Chaquopy Python files
-keep class com.chaquo.python.** { *; }

# Keep Python modules
-keepclassmembers class * {
    @com.chaquo.python.PyMethodProxy <methods>;
}
