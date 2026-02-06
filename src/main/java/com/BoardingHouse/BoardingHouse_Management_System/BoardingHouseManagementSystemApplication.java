package com.BoardingHouse.BoardingHouse_Management_System;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import com.BoardingHouse.BoardingHouse_Management_System.config.JwtConfig;

@EnableConfigurationProperties(JwtConfig.class)
@SpringBootApplication
public class BoardingHouseManagementSystemApplication {

	public static void main(String[] args) {
		SpringApplication.run(BoardingHouseManagementSystemApplication.class, args);
	}

}
