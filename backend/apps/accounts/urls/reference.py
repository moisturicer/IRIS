from django.urls import path
from apps.accounts import views

urlpatterns = [
    path("colleges/",                     views.CollegeListView.as_view(),     name="college-list"),
    path("departments/",                  views.DepartmentListView.as_view(),  name="department-list"),
    path("courses/",                      views.CourseListView.as_view(),      name="course-list"),
    path("settings/<str:key>/",           views.SystemSettingView.as_view(),   name="system-setting"),
]
